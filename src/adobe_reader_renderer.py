# -*- coding: utf-8 -*-
"""
Adobe Reader / Acrobat 渲染辅助模块 — 解决亿赛通 DLP 拦截 PDF 直接读取的问题

原理：
  亿赛通（DLP）会在驱动层拦截普通进程对受保护 PDF 的文件 I/O，
  导致 fitz.open() / pdfplumber / PyPDF2 等库读取失败。
  但 Adobe Reader / Acrobat 是亿赛通白名单内的受信任进程，
  它能通过 Windows API 拿到解密后的文件内容。

  本模块通过 COM (AcroExch.App / AcroExch.AVDoc / PDDoc) 调用 Adobe 打开 PDF，
  然后让 Adobe 把解密后的内容另存为临时 PDF，最后再用 PyMuPDF 把临时 PDF
  渲染成图片，ReportChecker 后续只需对这些图片做 OCR / 文字识别。

依赖：
  - Adobe Reader / Acrobat 已安装（系统须有 AcroExch.App COM 组件）
  - Windows + pywin32（pip install pywin32）
  - PyMuPDF (fitz) 用于渲染临时 PDF

用法示例：
    from adobe_reader_renderer import AdobeReaderRenderer

    renderer = AdobeReaderRenderer()
    if renderer.is_available():
        image_paths = renderer.render_pdf_to_images(r"D:/被亿赛通锁的.pdf", dpi=150)
        for path in image_paths:
            print("已生成:", path)
    else:
        print("未检测到 Adobe Reader / Acrobat，请确认已安装")
"""

import os
import sys
import shutil
import tempfile
import ctypes
from typing import Optional, List


# 常见 Adobe Reader / Acrobat 安装路径（按优先级匹配）
_ADOBE_CANDIDATE_PATHS = [
    # Adobe Acrobat DC / Pro（完整版，优先匹配）
    r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
    r"C:\Program Files (x86)\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
    r"C:\Program Files\Adobe\Acrobat 2020\Acrobat\Acrobat.exe",
    r"C:\Program Files (x86)\Adobe\Acrobat 2020\Acrobat\Acrobat.exe",
    r"C:\Program Files\Adobe\Acrobat 2017\Acrobat\Acrobat.exe",
    r"C:\Program Files (x86)\Adobe\Acrobat 2017\Acrobat\Acrobat.exe",
    # Adobe Acrobat Pro 旧版路径
    r"C:\Program Files\Adobe\Acrobat 11.0\Acrobat\Acrobat.exe",
    r"C:\Program Files (x86)\Adobe\Acrobat 11.0\Acrobat\Acrobat.exe",
    r"C:\Program Files\Adobe\Acrobat 10.0\Acrobat\Acrobat.exe",
    r"C:\Program Files (x86)\Adobe\Acrobat 10.0\Acrobat\Acrobat.exe",
    r"C:\Program Files\Adobe\Acrobat 9.0\Acrobat\Acrobat.exe",
    r"C:\Program Files (x86)\Adobe\Acrobat 9.0\Acrobat\Acrobat.exe",
    # Adobe Acrobat Reader DC / Reader
    r"C:\Program Files\Adobe\Acrobat DC\Reader\AcroRd32.exe",
    r"C:\Program Files (x86)\Adobe\Acrobat DC\Reader\AcroRd32.exe",
    r"C:\Program Files\Adobe\Reader 11.0\Reader\AcroRd32.exe",
    r"C:\Program Files (x86)\Adobe\Reader 11.0\Reader\AcroRd32.exe",
    r"C:\Program Files\Adobe\Reader 10.0\Reader\AcroRd32.exe",
    r"C:\Program Files (x86)\Adobe\Reader 10.0\Reader\AcroRd32.exe",
    r"C:\Program Files\Adobe\Reader 9.0\Reader\AcroRd32.exe",
    r"C:\Program Files (x86)\Adobe\Reader 9.0\Reader\AcroRd32.exe",
]


def find_adobe_reader() -> Optional[str]:
    """查找系统上已安装的 Adobe Reader / Acrobat 可执行文件路径。"""
    # 1) 先遍历候选路径
    for p in _ADOBE_CANDIDATE_PATHS:
        if os.path.exists(p):
            return p
    # 2) 尝试从注册表读取 Acrobat 安装路径
    if sys.platform == "win32":
        try:
            import winreg
            for sub in (r"SOFTWARE\Adobe\Adobe Acrobat\DC",
                        r"SOFTWARE\WOW6432Node\Adobe\Adobe Acrobat\DC"):
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub) as key:
                        val, _ = winreg.QueryValueEx(key, "InstallPath")
                    for name in ("Acrobat.exe", "AcroRd32.exe"):
                        candidate = os.path.join(val, name)
                        if os.path.exists(candidate):
                            return candidate
                except OSError:
                    continue
        except Exception:
            pass
    # 3) 最后尝试 PATH 查找
    for exe in ("AcroRd32.exe", "Acrobat.exe"):
        found = shutil.which(exe)
        if found and os.path.exists(found):
            return found
    return None


class AdobeReaderRenderer:
    """通过 COM 调 Adobe Reader / Acrobat 把 PDF 渲染成图片，绕过亿赛通 DLP 文件拦截。"""

    APP_PROGID = "AcroExch.App"

    def __init__(self):
        self._exe_path: Optional[str] = None
        self._app = None
        self._init()

    def _init(self):
        self._exe_path = find_adobe_reader()
        if sys.platform != "win32":
            return
        try:
            import win32com.client  # noqa: F401
        except Exception:
            pass

    def is_available(self) -> bool:
        return self._exe_path is not None

    def get_exe_path(self) -> Optional[str]:
        return self._exe_path

    def _create_app(self):
        """懒加载 Adobe COM App 对象。"""
        if self._app is not None:
            return self._app
        if not self.is_available():
            raise RuntimeError("未找到 Adobe Reader / Acrobat，无法使用 COM 接口")
        try:
            import win32com.client
            self._app = win32com.client.Dispatch(self.APP_PROGID)
            try:
                self._app.ShowToolbar = False
            except Exception:
                pass
            try:
                self._app.Visible = False
            except Exception:
                pass
            return self._app
        except Exception as e:
            raise RuntimeError(f"创建 Adobe COM 对象失败: {e}") from e

    def _close_app(self):
        try:
            if self._app is not None:
                try:
                    self._app.Exit()
                except Exception:
                    pass
                self._app = None
        except Exception:
            pass

    def render_pdf_to_images(self, pdf_path: str, dpi: int = 200,
                              output_dir: Optional[str] = None) -> List[str]:
        """通过 Adobe Reader / Acrobat COM 把 PDF 每一页渲染成 PNG，返回图片路径列表。

        实现策略（兼容 Reader 与 Acrobat DC）：

        思路核心：亿赛通 DLP 拦截普通进程对加密 PDF 的文件 I/O，但 Adobe Reader / Acrobat
        在白名单中，可以直接打开加密文件。我们用 COM 打开 PDF 后，让 Adobe 把内容
        另存为一个**未加密的临时 PDF**，再交由 PyMuPDF 渲染成图片。

        步骤：
            1. 启动 AcroExch.App，延迟加载
            2. 创建 AVDoc → 打开原始 PDF
            3. PDDoc.Save 另存为临时未加密 PDF
            4. 关闭 COM 文档
            5. 用 fitz 打开临时 PDF，逐页 get_pixmap → 保存为 PNG
            6. 删除临时 PDF
        """
        if not self.is_available():
            raise RuntimeError("未检测到 Adobe Reader / Acrobat，请确认已安装")
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix="reportchecker_adobe_")
        os.makedirs(output_dir, exist_ok=True)

        # 延迟 import（仅在需要时引入）
        try:
            import fitz  # PyMuPDF
        except Exception as e:
            raise RuntimeError(
                "render_pdf_to_images 需要 PyMuPDF（fitz），但未找到：%s" % e
            ) from e

        av_doc = None
        try:
            # 1) 创建 App + AVDoc
            self._create_app()
            import win32com.client
            av_doc = win32com.client.Dispatch("AcroExch.AVDoc")
            if not av_doc.Open(pdf_path, ""):
                raise RuntimeError(
                    f"Adobe Reader / Acrobat 无法打开 PDF（可能需要密码或文件被锁定）: {pdf_path}"
                )

            # 2) 获取 PDDoc 并 Save 为临时未加密 PDF
            pd_doc = av_doc.GetPDDoc()
            page_count = 0
            try:
                page_count = int(pd_doc.GetNumPages())
            except Exception as e:
                raise RuntimeError(f"无法获取 PDF 页数: {e}") from e
            if page_count <= 0:
                raise RuntimeError("PDF 页数为 0，文件无效")

            temp_pdf = os.path.join(output_dir, "_decrypted_tmp.pdf")
            # PDSaveFull = 1：完整保存
            # 尝试多种 flags，兼容不同 Reader/Acrobat 版本
            saved = False
            for nFlags in (1, 2, 1 | 16, 2 | 16):
                try:
                    if pd_doc.Save(nFlags, temp_pdf):
                        if os.path.exists(temp_pdf) and os.path.getsize(temp_pdf) > 0:
                            saved = True
                            break
                except Exception:
                    continue
            if not saved or not os.path.exists(temp_pdf):
                raise RuntimeError("Acrobat COM 另存 PDF 失败：解密/保存过程出错")

            # 3) 关闭 COM 文档，释放文件句柄
            try:
                av_doc.Close(True)
            except Exception:
                pass
            av_doc = None
            try:
                pd_doc.Close()
            except Exception:
                pass

            # 4) 用 fitz 打开临时 PDF，逐页渲染为图片
            image_paths: List[str] = []
            try:
                tmp_doc = fitz.open(temp_pdf)
            except Exception as e:
                raise RuntimeError(f"另存后的 PDF 无法被 fitz 打开: {e}") from e

            try:
                zoom = max(0.5, dpi / 72.0)
                mat = fitz.Matrix(zoom, zoom)
                for page_idx in range(tmp_doc.page_count):
                    page = tmp_doc.load_page(page_idx)
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    out_path = os.path.join(
                        output_dir, f"page_{page_idx + 1:04d}.png"
                    )
                    pix.save(out_path)
                    image_paths.append(out_path)
            finally:
                try:
                    tmp_doc.close()
                except Exception:
                    pass

            # 5) 删除临时 PDF（保留图片）
            try:
                os.remove(temp_pdf)
            except Exception:
                pass

            return image_paths
        finally:
            if av_doc is not None:
                try:
                    av_doc.Close(True)
                except Exception:
                    pass

    def __del__(self):
        try:
            self._close_app()
        except Exception:
            pass


# =========================== 便捷函数 ===========================

def render_pdf_with_adobe(pdf_path: str, dpi: int = 200,
                          output_dir: Optional[str] = None) -> List[str]:
    """快捷函数：用 Adobe Reader / Acrobat 渲染 PDF 到图片。"""
    renderer = AdobeReaderRenderer()
    if not renderer.is_available():
        raise RuntimeError("未检测到 Adobe Reader / Acrobat，请先安装")
    return renderer.render_pdf_to_images(pdf_path, dpi=dpi, output_dir=output_dir)


if __name__ == "__main__":
    print("=" * 60)
    print("Adobe Reader / Acrobat Renderer Self-Check")
    print("=" * 60)
    path = find_adobe_reader()
    if path:
        print(f"[OK] Found Adobe: {path}")
    else:
        print("[FAIL] Adobe Reader / Acrobat not found. Please install first.")
        sys.exit(1)

    if len(sys.argv) >= 2:
        test_pdf = sys.argv[1]
        try:
            imgs = render_pdf_with_adobe(test_pdf, dpi=150)
            print(f"[OK] Rendered {len(imgs)} page(s):")
            for p in imgs[:5]:
                print(f"  - {p}")
            if len(imgs) > 5:
                print(f"  ... {len(imgs)} pages total")
        except Exception as e:
            print(f"[FAIL] Render failed: {e}")
            sys.exit(2)
