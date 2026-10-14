# -*- coding: utf-8 -*-
"""
Adobe Acrobat 窗口捕获模块 —— 不打开文件，直接检测已打开的 Adobe PDF 窗口进行识别

原理：
  亿赛通 DLP 拦截了普通进程对受保护 PDF 的文件 I/O，即使用 COM 的
  AVDoc.Open() 也可能失败（因为底层仍需要文件 I/O）。
  
  但用户可以先手动用 Adobe Acrobat 打开 PDF（Acrobat 在 DLP 白名单中），
  本模块通过以下方式工作：
  
  1. COM 连接到已运行的 Acrobat 实例（GetObject），获取当前已打开的 AVDoc/PDDoc
  2. 获取总页数
  3. 截图 Acrobat 窗口 → 裁剪出 PDF 页面区域 → 得到页面图像
  4. 可通过 COM 控制 Acrobat 翻页

依赖：
  - Adobe Acrobat（已运行并打开了目标 PDF）
  - Windows + pywin32 + Pillow
  - win32gui / win32ui（Windows 截图）

用法：
    from adobe_window_capture import AdobeWindowCapture
    
    cap = AdobeWindowCapture()
    if cap.connect():
        print(f"已连接 Acrobat，当前文档 {cap.page_count} 页")
        img = cap.capture_current_page()  # numpy array (H, W, 3)
"""

import os
import sys
import time
import ctypes
from typing import Optional, Tuple, List
from ctypes import wintypes

import numpy as np
from PIL import Image


# =========================== Windows GDI 截图工具 ===========================

def _get_acrobat_window_handle() -> Optional[int]:
    """查找当前正在运行的 Adobe Acrobat / Adobe Reader 主窗口句柄。

    同时检测以下进程：
      - Acrobat.exe   (Adobe Acrobat DC / Pro)
      - AcroRd32.exe  (Adobe Reader)
      - AcrobatSEC.exe(亿赛通加固版)
    """
    import win32gui
    import win32process
    import win32api

    # 进程名白名单
    _VALID_EXES = {'acrobat.exe', 'acrord32.exe', 'acrobatsec.exe'}

    def enum_callback(hwnd, results):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title or len(title) < 3:
            return True
        lower = title.lower()
        # 匹配各种 Adobe 窗口标题格式：
        #   "xxx.pdf - Adobe Acrobat"
        #   "xxx.pdf - Adobe Acrobat Pro DC"
        #   "xxx.pdf - Adobe Acrobat Reader DC"
        #   "xxx.pdf - Adobe Reader"
        #   "Adobe Acrobat" (无文件名)
        if any(kw in lower for kw in (
            'adobe acrobat', 'adobe reader', '.pdf'
        )):
            # 确认进程是 Acrobat.exe / AcroRd32.exe / AcrobatSEC.exe
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid:
                    handle = win32api.OpenProcess(0x0400 | 0x0010, False, pid)
                    try:
                        exe_name = win32process.GetModuleFileNameEx(handle, 0)
                        exe_base = os.path.basename(exe_name).lower()
                        if exe_base in _VALID_EXES:
                            results.append(hwnd)
                    finally:
                        win32api.CloseHandle(handle)
            except Exception:
                # OpenProcess 可能因权限不足失败，用标题匹配做回退
                if 'adobe' in lower:
                    results.append(hwnd)
        return True

    results = []
    try:
        win32gui.EnumWindows(enum_callback, results)
    except Exception:
        pass
    return results[0] if results else None


def _capture_window(hwnd: int) -> Optional[np.ndarray]:
    """截取指定窗口的完整画面，返回 numpy array (H, W, 3) RGB。"""
    import win32gui
    import win32ui
    import win32con

    try:
        # 确保窗口可见
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            return None

        # 获取窗口 DC
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()

        # 创建位图
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bitmap)

        # 使用 PrintWindow 截取（比 BitBlt 更可靠，可以截取被遮挡的窗口）
        result = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)  # PW_RENDERFULLCONTENT=2
        if result == 0:
            # 尝试 PW_CLIENTONLY=1
            result = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 1)
        if result == 0:
            # 回退到 BitBlt
            save_dc.BitBlt((0, 0), (width, height), mfc_dc, (0, 0), win32con.SRCCOPY)

        # 转为 PIL Image
        bmp_info = bitmap.GetInfo()
        bmp_bits = bitmap.GetBitmapBits(True)
        img = Image.frombuffer(
            'RGB',
            (bmp_info['bmWidth'], bmp_info['bmHeight']),
            bmp_bits, 'raw', 'BGRX', 0, 1
        )

        # 清理
        win32gui.DeleteObject(bitmap.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)

        return np.array(img)
    except Exception as e:
        print(f"[WindowCapture] 截图失败: {e}")
        return None


# =========================== Acrobat 窗口区域检测 ===========================

def _find_pdf_view_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """
    在 Acrobat/Reader 窗口中精确查找 PDF 页面显示区域。

    Acrobat DC 的所有子窗口类名都是 AVL_AVView，需要通过 GetWindowText
    来区分，找到 text 为 "AVPageView" 或 "AVScrolledPageView" 的子窗口。

    返回相对于窗口的 (left, top, right, bottom)，或 None。
    """
    import win32gui
    import win32con

    best_match = None
    best_area = 0

    def find_page_view_child(parent, depth=0):
        nonlocal best_match, best_area
        if depth > 12:
            return
        try:
            child = win32gui.GetWindow(parent, win32con.GW_CHILD)
            while child:
                class_name = win32gui.GetClassName(child)
                text = win32gui.GetWindowText(child)
                rect = win32gui.GetWindowRect(child)
                parent_rect = win32gui.GetWindowRect(hwnd)
                rel = (
                    rect[0] - parent_rect[0],
                    rect[1] - parent_rect[1],
                    rect[2] - parent_rect[0],
                    rect[3] - parent_rect[1],
                )
                w = rel[2] - rel[0]
                h = rel[3] - rel[1]
                area = w * h

                # 精确匹配 AVPageView（通过 text 字段）
                if text == "AVPageView" and area > best_area:
                    best_match = rel
                    best_area = area

                # 次选：AVScrolledPageView
                elif text == "AVScrolledPageView" and area > best_area:
                    best_match = rel
                    best_area = area

                # 递归
                find_page_view_child(child, depth + 1)
                child = win32gui.GetWindow(child, win32con.GW_HWNDNEXT)
        except Exception:
            pass

    find_page_view_child(hwnd)
    return best_match


def _estimate_pdf_view_rect(hwnd: int) -> Tuple[int, int, int, int]:
    """
    估算 PDF 页面在 Acrobat 窗口中的显示区域。
    当无法精确找到 AVPageView 子窗口时，使用启发式方法：
    - 去掉顶部工具栏（约 80px）
    - 去掉底部状态栏（约 30px）
    - 去掉左侧导航面板（如果有，约 240px）
    """
    import win32gui

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    w = right - left
    h = bottom - top

    # 启发式边距
    toolbar_top = 90       # 顶部菜单+工具栏
    status_bottom = 35     # 底部状态栏
    nav_left = 0           # 默认无导航面板

    # 检查左侧是否有导航面板（窗口宽度 > 800 时可能有）
    if w > 1000:
        nav_left = 240

    rel = (nav_left, toolbar_top, w, h - status_bottom)
    return rel


# =========================== AdobeWindowCapture 主类 ===========================

class AdobeWindowCapture:
    """连接到已运行的 Adobe Acrobat 窗口，捕获页面图像。"""

    def __init__(self):
        self._hwnd: Optional[int] = None
        self._app = None
        self._av_doc = None
        self._pd_doc = None
        self._page_count: int = 0
        self._current_page: int = 0
        self._window_title: str = ""
        self._pdf_view_rect: Optional[Tuple[int, int, int, int]] = None
        self._connected: bool = False

    def is_available(self) -> bool:
        """检查是否有可用的 Acrobat 窗口。"""
        hwnd = _get_acrobat_window_handle()
        return hwnd is not None

    def connect(self) -> bool:
        """
        连接到已运行的 Acrobat 实例。
        返回 True 表示成功连接，可以开始捕获。
        """
        if self._connected:
            return True

        # 1. 找到 Acrobat 窗口
        hwnd = _get_acrobat_window_handle()
        if not hwnd:
            print("[AdobeWindowCapture] 未找到正在运行的 Adobe Acrobat 窗口")
            return False

        import win32gui
        self._hwnd = hwnd
        self._window_title = win32gui.GetWindowText(hwnd)
        print(f"[AdobeWindowCapture] 找到 Acrobat 窗口: {self._window_title}")

        # 2. 尝试 COM 连接到已运行的实例
        try:
            import win32com.client
            import pythoncom
            # GetObject 获取已运行的 Acrobat 实例（不创建新的）
            pythoncom.CoInitialize()
            try:
                self._app = win32com.client.GetObject(Class="AcroExch.App")
            except Exception:
                # 如果没有已运行的 COM 实例，尝试 Dispatch（可能会创建新实例）
                self._app = win32com.client.Dispatch("AcroExch.App")
        except Exception as e:
            print(f"[AdobeWindowCapture] COM 连接失败: {e}，将使用纯截图模式")
            self._app = None

        # 3. 获取当前文档信息
        if self._app is not None:
            try:
                self._av_doc = self._app.GetActiveDoc()
                if self._av_doc is not None:
                    self._pd_doc = self._av_doc.GetPDDoc()
                    self._page_count = int(self._pd_doc.GetNumPages())
                    print(f"[AdobeWindowCapture] 当前文档: {self._page_count} 页")
            except Exception as e:
                print(f"[AdobeWindowCapture] 获取文档信息失败: {e}")
                self._av_doc = None
                self._pd_doc = None

        # 如果 COM 获取页数失败，设一个大值让用户手动控制
        if self._page_count <= 0:
            self._page_count = 999
            print("[AdobeWindowCapture] 无法获取页数，假设为多页文档")

        # 4. 最大化窗口以获得最大截图分辨率
        self._maximize_window()

        # 5. 检测 PDF 视图区域
        self._pdf_view_rect = _find_pdf_view_rect(hwnd)
        if self._pdf_view_rect is None:
            self._pdf_view_rect = _estimate_pdf_view_rect(hwnd)
        print(f"[AdobeWindowCapture] PDF 视图区域: {self._pdf_view_rect}")

        # 6. 设置整页适应缩放，确保完整页面显示在视口中
        self._ensure_fit_page()

        self._connected = True
        return True

    def disconnect(self):
        """断开连接。"""
        self._hwnd = None
        self._app = None
        self._av_doc = None
        self._pd_doc = None
        self._page_count = 0
        self._current_page = 0
        self._window_title = ""
        self._pdf_view_rect = None
        self._connected = False

    def extract_text_via_com(self, page_num: int) -> Optional[str]:
        """通过 Acrobat COM 接口直接提取页面文本（不依赖截图OCR）

        优先于截图OCR使用，因为文本提取100%准确。
        如果COM不可用或文本提取失败，返回None，调用方回退到截图OCR。
        """
        if not self._pd_doc:
            return None
        try:
            js = self._pd_doc.GetJSObject()
            if js:
                text = js.getPageText(page_num)
                if text and text.strip():
                    return text.strip()
        except Exception:
            pass
        # 尝试用 PDPage 方式
        try:
            page = self._pd_doc.AcquirePage(page_num)
            if page:
                # PDPage.GetWords 返回单词列表（需要 AcroForm 插件支持）
                words = []
                num_words = page.GetNumWords()
                for i in range(num_words):
                    word = page.GetNthWord(i, True)  # True = include spaces
                    if word:
                        words.append(word)
                if words:
                    return ' '.join(words)
        except Exception:
            pass
        return None

    @property
    def has_com_text_extraction(self) -> bool:
        """是否可以通过COM提取文本"""
        return self._pd_doc is not None

    @property
    def page_count(self) -> int:
        return self._page_count

    @property
    def current_page(self) -> int:
        return self._current_page

    @property
    def window_title(self) -> str:
        return self._window_title

    def _maximize_window(self) -> bool:
        """最大化 Acrobat 窗口以获得最大截图分辨率。"""
        import win32gui
        import win32con
        if not self._hwnd:
            return False
        try:
            win32gui.ShowWindow(self._hwnd, win32con.SW_MAXIMIZE)
            time.sleep(0.3)
            return True
        except Exception as e:
            print(f"[AdobeWindowCapture] 最大化窗口失败: {e}")
            return False

    def _send_keys_to_acrobat(self, keys):
        """
        通过 keybd_event 向 Acrobat 窗口发送键盘组合键。
        用于在 COM 不可用时控制缩放、翻页等。

        Args:
            keys: 虚拟键码列表，最后一个是主键，前面的都是修饰键。
                  例如 Ctrl+0: [VK_CONTROL, 0x30]
                       PageDown: [VK_NEXT]
        """
        import win32gui
        import win32con
        import win32api

        if not self._hwnd:
            return False
        try:
            # 先把窗口置前
            win32gui.SetForegroundWindow(self._hwnd)
            time.sleep(0.2)

            # 按下修饰键
            for k in keys[:-1]:
                win32api.keybd_event(k, 0, 0, 0)
            # 按下并释放主键
            win32api.keybd_event(keys[-1], 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(keys[-1], 0, win32con.KEYEVENTF_KEYUP, 0)
            # 释放修饰键（倒序）
            for k in reversed(keys[:-1]):
                win32api.keybd_event(k, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.3)
            return True
        except Exception as e:
            print(f"[AdobeWindowCapture] 发送按键失败: {e}")
            return False

    def _ensure_fit_page(self) -> bool:
        """
        确保 Acrobat 以"整页适应"模式显示 PDF，使完整页面出现在视口中。

        策略（按优先级尝试）：
          1. COM SetZoomType(1)  — 精确控制（需要 Acrobat 完整版）
          2. 键盘模拟 Ctrl+0       — 适合页面（通用，Reader 也支持）
          3. 键盘模拟 Ctrl+1       — 适应宽度（Ctrl+0 不可用时的回退）
        """
        import win32gui
        import win32con

        # 方法 1: COM SetZoomType
        if self._av_doc is not None:
            try:
                page_view = self._av_doc.GetAVPageView()
                if page_view is not None:
                    page_view.SetZoomType(1)  # Fit Page
                    time.sleep(0.5)
                    new_rect = _find_pdf_view_rect(self._hwnd)
                    if new_rect is not None:
                        self._pdf_view_rect = new_rect
                    print(f"[AdobeWindowCapture] COM SetZoomType(1) OK")
                    return True
            except Exception as e:
                print(f"[AdobeWindowCapture] COM SetZoomType 失败: {e}")

        # 方法 2: 键盘模拟 Ctrl+0（适合页面，Acrobat 快捷键）
        print("[AdobeWindowCapture] 尝试键盘模拟 Ctrl+0 (适合页面)...")
        if self._send_keys_to_acrobat([win32con.VK_CONTROL, 0x30]):  # 0x30 = '0'
            time.sleep(0.5)
            new_rect = _find_pdf_view_rect(self._hwnd)
            if new_rect is not None:
                self._pdf_view_rect = new_rect
                print(f"[AdobeWindowCapture] Ctrl+0 OK, 视图区域: {self._pdf_view_rect}")
                return True

        # 方法 3: 键盘模拟 Ctrl+1（适应宽度）
        print("[AdobeWindowCapture] 尝试键盘模拟 Ctrl+1 (适应宽度)...")
        if self._send_keys_to_acrobat([win32con.VK_CONTROL, 0x31]):  # 0x31 = '1'
            time.sleep(0.5)
            new_rect = _find_pdf_view_rect(self._hwnd)
            if new_rect is not None:
                self._pdf_view_rect = new_rect
                print(f"[AdobeWindowCapture] Ctrl+1 OK, 视图区域: {self._pdf_view_rect}")
                return True

        # 全部失败，保持当前视图区域不变
        print("[AdobeWindowCapture] 无法设置缩放，使用当前视图区域")
        return False

    def goto_page(self, page_num: int) -> bool:
        """
        跳转到指定页面（0-based）。
        优先使用 COM，COM 不可用时通过键盘模拟翻页。
        """
        if not self._connected:
            return False
        if page_num < 0 or page_num >= self._page_count:
            return False

        # 方法 1: COM 翻页
        if self._av_doc is not None:
            try:
                page_view = self._av_doc.GetAVPageView()
                if page_view:
                    page_view.Goto(page_num)
                    self._current_page = page_num
                    self._ensure_fit_page()
                    return True
            except Exception as e:
                print(f"[AdobeWindowCapture] COM 翻页失败: {e}")

        # 方法 2: 键盘模拟翻页（Reader 也可用）
        import win32con
        if page_num > self._current_page:
            # 向后翻页：发送 PageDown
            diff = page_num - self._current_page
            for _ in range(diff):
                self._send_keys_to_acrobat([win32con.VK_NEXT])  # PageDown
                time.sleep(0.3)
            self._current_page = page_num
            return True
        elif page_num < self._current_page:
            # 向前翻页：发送 PageUp
            diff = self._current_page - page_num
            for _ in range(diff):
                self._send_keys_to_acrobat([win32con.VK_PRIOR])  # PageUp
                time.sleep(0.3)
            self._current_page = page_num
            return True

        return False

    def next_page(self) -> bool:
        """翻到下一页。"""
        return self.goto_page(self._current_page + 1)

    def prev_page(self) -> bool:
        """翻到上一页。"""
        return self.goto_page(self._current_page - 1)

    def capture_window_full(self) -> Optional[np.ndarray]:
        """截取整个 Acrobat 窗口。"""
        if not self._connected or self._hwnd is None:
            return None
        return _capture_window(self._hwnd)

    def _trim_to_content(self, img: np.ndarray) -> np.ndarray:
        """
        智能裁剪：去掉 Adobe 窗口四周的非页面区域（深灰侧边栏、工具栏等）。

        核心策略：PDF 页面是白色/浅色的，用列亮度直方图找到
        "连续白色区域"的左右边界。不依赖单列亮度（容易受噪声影响），
        而是看一段连续的列是否整体偏白。
        """
        if img is None or img.size == 0:
            return img

        h, w = img.shape[:2]
        if h < 20 or w < 20:
            return img

        # 计算每列的平均亮度
        col_brightness = np.mean(img.astype(np.float32), axis=(0, 2)) if len(img.shape) == 3 else np.mean(img.astype(np.float32), axis=0)
        # 计算每行的平均亮度
        row_brightness = np.mean(img.astype(np.float32), axis=(1, 2)) if len(img.shape) == 3 else np.mean(img.astype(np.float32), axis=1)

        # ── 左右裁剪：找连续白色区域的边界 ──
        # 用滑动窗口（宽度=总宽度的5%）找连续偏白区域
        win = max(5, w // 20)

        # 左边界：从左向右扫描，找到第一个"窗口内平均亮度 > 180"的位置
        left = 0
        for x in range(w - win):
            window_avg = np.mean(col_brightness[x:x + win])
            if window_avg > 180:
                left = x
                break

        # 右边界：从右向左扫描
        right = w
        for x in range(w - win, -1, -1):
            end = min(x + win, w)
            window_avg = np.mean(col_brightness[x:end])
            if window_avg > 180:
                right = end
                break

        # ── 上下裁剪 ──
        top = 0
        for y in range(h):
            if row_brightness[y] > 170:
                top = y
                break

        bottom = h
        for y in range(h - 1, -1, -1):
            if row_brightness[y] > 170:
                bottom = y + 1
                break

        # 确保裁剪后有效
        if bottom - top < 20 or right - left < 20:
            return img

        # 保留少量边距
        pad = 2
        top = max(0, top - pad)
        left = max(0, left - pad)
        bottom = min(h, bottom + pad)
        right = min(w, right + pad)

        result = img[top:bottom, left:right]

        # ── 二次清理：逐列扫描，去掉边缘残留的深灰列 ──
        if result.shape[0] > 10 and result.shape[1] > 10:
            col_b = np.mean(result.astype(np.float32), axis=(0, 2)) if len(result.shape) == 3 else np.mean(result.astype(np.float32), axis=0)
            # 找到所有亮度 > 190 的列（确定为白色页面区域）
            bright_cols = np.where(col_b > 190)[0]
            if len(bright_cols) > 5:
                final_left = max(0, bright_cols[0] - 2)
                final_right = min(result.shape[1], bright_cols[-1] + 3)
                if final_right - final_left > 10:
                    result = result[:, final_left:final_right]

        return result

    def capture_current_page(self) -> Optional[np.ndarray]:
        """
        截取当前 Acrobat 窗口中 PDF 页面的显示区域。
        返回 RGB numpy array。
        """
        full_img = self.capture_window_full()
        if full_img is None:
            return None

        if self._pdf_view_rect is None:
            return full_img

        left, top, right, bottom = self._pdf_view_rect
        h, w = full_img.shape[:2]

        # 确保坐标在有效范围内
        left = max(0, min(left, w - 1))
        top = max(0, min(top, h - 1))
        right = max(left + 1, min(right, w))
        bottom = max(top + 1, min(bottom, h))

        cropped = full_img[top:bottom, left:right]

        # 智能裁剪掉灰色背景边缘，只保留白色页面区域
        cropped = self._trim_to_content(cropped)

        return cropped

    def render_all_pages(self, output_dir: Optional[str] = None,
                          progress_callback=None) -> List[str]:
        """
        自动翻页截取所有页面，保存为 PNG。

        Args:
            output_dir: 输出目录（None 则使用临时目录）
            progress_callback: 进度回调 func(current_page, total_pages)

        Returns:
            图片文件路径列表
        """
        import tempfile
        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix="reportchecker_live_")
        os.makedirs(output_dir, exist_ok=True)

        image_paths = []
        for i in range(self._page_count):
            if progress_callback:
                progress_callback(i + 1, self._page_count)

            # 翻到目标页
            if not self.goto_page(i):
                print(f"[AdobeWindowCapture] 无法翻到第 {i + 1} 页，尝试截图当前页")
            else:
                # 等待页面渲染
                time.sleep(0.5)

            img = self.capture_current_page()
            if img is not None:
                out_path = os.path.join(output_dir, f"page_{i + 1:04d}.png")
                Image.fromarray(img).save(out_path)
                image_paths.append(out_path)

        return image_paths

    def capture_current_page_save(self, output_path: str) -> bool:
        """截取当前页并保存为文件。"""
        img = self.capture_current_page()
        if img is None:
            return False
        try:
            Image.fromarray(img).save(output_path)
            return True
        except Exception as e:
            print(f"[AdobeWindowCapture] 保存失败: {e}")
            return False


# =========================== 便捷函数 ===========================

def capture_adobe_window_to_image(output_path: Optional[str] = None) -> Optional[np.ndarray]:
    """快捷函数：截取当前 Acrobat 窗口的 PDF 页面区域。"""
    cap = AdobeWindowCapture()
    if not cap.connect():
        print("[capture_adobe_window_to_image] 未找到 Acrobat 窗口")
        return None
    img = cap.capture_current_page()
    if img is not None and output_path:
        Image.fromarray(img).save(output_path)
    cap.disconnect()
    return img


# =========================== 自检 ===========================

if __name__ == "__main__":
    print("=" * 60)
    print("Adobe Acrobat Window Capture - Self Check")
    print("=" * 60)

    cap = AdobeWindowCapture()
    if not cap.is_available():
        print("[FAIL] No Adobe Acrobat window found. Please open a PDF in Acrobat first.")
        sys.exit(1)

    if not cap.connect():
        print("[FAIL] Failed to connect to Acrobat.")
        sys.exit(1)

    print(f"[OK] Connected: {cap.window_title}")
    print(f"[OK] Page count: {cap.page_count}")

    # 截取当前页
    img = cap.capture_current_page()
    if img is not None:
        out = os.path.join(tempfile.gettempdir(), "acrobat_capture_test.png")
        Image.fromarray(img).save(out)
        print(f"[OK] Captured page saved to: {out}")
        print(f"[OK] Image size: {img.shape[1]}x{img.shape[0]}")
    else:
        print("[FAIL] Failed to capture page.")

    cap.disconnect()
