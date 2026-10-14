"""
工具函数模块
提供数值解析、坐标转换、JSON 读写等通用功能
"""

import json
import re
import numpy as np
from typing import Optional, Dict, Any, Tuple


def parse_number(text: str) -> Optional[float]:
    """
    从文本中解析数值，处理各种格式异常

    支持：正负号、千分位逗号、小数、科学计数法、比较符前缀(≤ ≥ < >)、
    范围取较大值等。优先匹配带符号/带逗号的小数，避免误取序号。

    Args:
        text: 待解析的文本

    Returns:
        解析后的浮点数，解析失败返回 None

    Example:
        >>> parse_number("85.5K")
        85.5
        >>> parse_number("≤5mA")
        5.0
        >>> parse_number("-1,234.5")
        -1234.5
        >>> parse_number("N/A")
        None
    """
    if not text or not isinstance(text, str):
        return None

    text = text.strip()
    if not text or text.upper() in ("N/A", "NA", "无", "—", "-", "合格", "PASS", "OK"):
        return None

    # 1) 优先匹配带符号、千分位、科学计数法的完整数字
    #    形如 -1,234.56 / +3.2e-3 / 1.5×10³
    full_pat = re.compile(
        r'[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?'   # 千分位或普通小数
        r'(?:[eE][-+]?\d+)?'                    # 科学计数法
    )
    m = full_pat.search(text)
    if m:
        try:
            val = float(m.group(0).replace(',', ''))
            # 过滤明显非数值（如纯年份 2024 在测试数据中极少作为测量值，保留）
            return val
        except ValueError:
            pass

    # 2) 兜底：匹配任意小数/整数（含比较符前缀）
    patterns = [
        r'≤\s*([-+]?\d[\d.,]*)',
        r'≥\s*([-+]?\d[\d.,]*)',
        r'<\s*([-+]?\d[\d.,]*)',
        r'>\s*([-+]?\d[\d.,]*)',
        r'([-+]?\d[\d.,]*)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return float(match.group(1).replace(',', ''))
            except ValueError:
                continue

    return None


def parse_int(text: str) -> Optional[int]:
    """
    从文本中解析整数
    
    Args:
        text: 待解析的文本
        
    Returns:
        解析后的整数，解析失败返回 None
    """
    num = parse_number(text)
    if num is not None:
        return int(round(num))
    return None


def convert_pdf_rect_to_pixmap(rect: Tuple[float, float, float, float], 
                               page_height: float, 
                               pixmap_height: int) -> Tuple[int, int, int, int]:
    """
    将 PDF 坐标矩形转换为 Pixmap 图像坐标矩形
    
    PDF 坐标原点在左下角，Pixmap 坐标原点在左上角
    
    Args:
        rect: PDF 矩形 (x0, y0, x1, y1)
        page_height: PDF 页面高度（点）
        pixmap_height: Pixmap 图像高度（像素）
        
    Returns:
        Pixmap 矩形 (left, top, right, bottom)
    """
    x0, y0, x1, y1 = rect
    
    scale = pixmap_height / page_height
    
    left = int(x0 * scale)
    bottom = int(y0 * scale)
    right = int(x1 * scale)
    top = int(y1 * scale)
    
    pixmap_top = pixmap_height - top
    pixmap_bottom = pixmap_height - bottom
    
    return (left, pixmap_top, right, pixmap_bottom)


def read_json_file(file_path: str) -> Optional[Dict[str, Any]]:
    """
    读取 JSON 文件
    
    Args:
        file_path: JSON 文件路径
        
    Returns:
        JSON 数据字典，读取失败返回 None
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None
    except Exception:
        return None


def write_json_file(file_path: str, data: Dict[str, Any]) -> bool:
    """
    写入 JSON 文件
    
    Args:
        file_path: JSON 文件路径
        data: 要写入的数据
        
    Returns:
        是否写入成功
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def format_error_message(field_name: str, 
                        error_type: str, 
                        actual_value: Any, 
                        expected_value: Any = None,
                        unit: str = "") -> str:
    """
    格式化错误信息
    
    Args:
        field_name: 字段名称
        error_type: 错误类型 (warning/error)
        actual_value: 实际值
        expected_value: 期望值
        unit: 单位
        
    Returns:
        格式化后的错误消息
    """
    unit_str = f" {unit}" if unit else ""
    
    if error_type == "missing":
        return f"[缺失] {field_name} 未填写"
    elif error_type == "warning":
        if expected_value is not None:
            return f"[警告] {field_name} = {actual_value}{unit_str}，与期望 {expected_value}{unit_str} 偏差较大"
        return f"[警告] {field_name} = {actual_value}{unit_str}"
    elif error_type == "limit_exceeded":
        return f"[超限] {field_name} = {actual_value}{unit_str}，超过限值 {expected_value}{unit_str}"
    elif error_type == "calculation_mismatch":
        return f"[计算异常] {field_name} 计算值与记录值不一致"
    else:
        return f"[异常] {field_name} = {actual_value}{unit_str}"


def calculate_temperature_rise(hot_temp: float, room_temp: float) -> float:
    """
    计算温升 ΔT = T_hot - T_room
    
    Args:
        hot_temp: 热态温度
        room_temp: 室温
        
    Returns:
        温升值
    """
    return hot_temp - room_temp


def check_tolerance(value: float, expected: float, tolerance: float = 0.5) -> bool:
    """
    检查值是否在容差范围内
    
    Args:
        value: 实际值
        expected: 期望值
        tolerance: 容差范围
        
    Returns:
        是否在容差范围内
    """
    return abs(value - expected) <= tolerance


def check_limit(value: float, limit: float, operator: str = "<=") -> bool:
    """
    检查值是否符合限值要求
    
    Args:
        value: 实际值
        limit: 限值
        operator: 比较运算符 (<=, >=, <, >)
        
    Returns:
        是否符合限值要求
    """
    if operator == "<=":
        return value <= limit
    elif operator == ">=":
        return value >= limit
    elif operator == "<":
        return value < limit
    elif operator == ">":
        return value > limit
    return False


def find_number_regions(text_results: list) -> list:
    """
    从OCR识别结果中找出包含数字的区域
    
    PaddleOCR 返回格式: [ [ [box_pts], (text, conf) ], ... ]
    
    Args:
        text_results: OCR识别结果列表
        
    Returns:
        包含数字的区域列表
    """
    number_regions = []
    number_pattern = re.compile(r'\d')
    
    if not text_results:
        return number_regions
    
    for item in text_results:
        try:
            if not isinstance(item, list) or len(item) < 2:
                continue
            
            box = item[0]
            text_info = item[1]
            
            if isinstance(text_info, (list, tuple)) and len(text_info) > 0:
                text = text_info[0]
            else:
                text = str(text_info)
            
            if not number_pattern.search(text):
                continue
            
            if not isinstance(box, list) or len(box) < 4:
                continue
            
            xs = [pt[0] for pt in box]
            ys = [pt[1] for pt in box]
            
            number_regions.append({
                'x0': min(xs),
                'y0': min(ys),
                'x1': max(xs),
                'y1': max(ys),
                'text': text
            })
        except Exception:
            continue
    
    return number_regions


def draw_ocr_boxes(image_array: np.ndarray, ocr_result: list,
                  color=(0, 200, 255)) -> np.ndarray:
    """
    在图像上画出 OCR 识别到的所有文字/数字框，并标注识别文本。

    Args:
        image_array: 图像数组（RGB）
        ocr_result: OCR 引擎原始返回（PaddleOCR/RapidOCR 风格：
                     [[[box_pts], (text, conf)], ...]）
        color: 框线颜色 (B, G, R)

    Returns:
        带识别框的图像数组
    """
    import cv2

    result_img = image_array.copy()
    if not ocr_result:
        return result_img

    try:
        items = ocr_result[0] if (isinstance(ocr_result, list) and len(ocr_result) == 1
                                   and isinstance(ocr_result[0], list)) else ocr_result
    except Exception:
        items = ocr_result

    for item in items:
        try:
            if not isinstance(item, list) or len(item) < 2:
                continue
            box = item[0]
            text_info = item[1]
            if isinstance(text_info, (list, tuple)) and len(text_info) > 0:
                text = str(text_info[0])
            else:
                text = str(text_info)

            if not isinstance(box, list) or len(box) < 4:
                continue

            pts = np.array([[int(float(p[0])), int(float(p[1]))] for p in box], np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(result_img, [pts], True, color, 2)

            x = int(min(p[0] for p in box))
            y = int(min(p[1] for p in box))
            if text:
                cv2.putText(result_img, text[:20], (max(0, x), max(12, y - 4)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
        except Exception:
            continue

    return result_img


def highlight_number_regions(image_array: np.ndarray, regions: list,
                             page_height: float = None,
                             coords_are_pixels: bool = False) -> np.ndarray:
    """
    在图像上高亮显示数字区域

    Args:
        image_array: 图像数组
        regions: 区域列表
        page_height: PDF页面高度（仅当 coords_are_pixels=False 时使用）
        coords_are_pixels: 区域坐标是否已经是图像像素坐标。
            - False（默认）：region 坐标为 PDF 点坐标，需按 page_height 缩放
            - True：region 坐标已是图像像素坐标，直接使用（OCR 全页识别结果）

    Returns:
        高亮后的图像数组
    """
    import cv2

    result_img = image_array.copy()
    img_h, img_w = image_array.shape[0], image_array.shape[1]

    for region in regions:
        if coords_are_pixels:
            # OCR 返回的坐标即图像像素坐标，直接使用（左上角原点）
            x0 = int(region['x0'])
            y0 = int(region['y0'])
            x1 = int(region['x1'])
            y1 = int(region['y1'])
            top = min(y0, y1)
            bottom = max(y0, y1)
            left = min(x0, x1)
            right = max(x0, x1)
        else:
            scale = img_h / page_height if page_height else 1.0
            x0 = int(region['x0'] * scale)
            y0 = int(region['y0'] * scale)
            x1 = int(region['x1'] * scale)
            y1 = int(region['y1'] * scale)
            top = img_h - y1
            bottom = img_h - y0
            left = x0
            right = x1

        # 边界修正
        left = max(0, left)
        top = max(0, top)
        right = min(img_w, right)
        bottom = min(img_h, bottom)

        if left < right and top < bottom:
            overlay = result_img.copy()
            cv2.rectangle(overlay, (left, top), (right, bottom), (0, 255, 255), -1)
            result_img = cv2.addWeighted(overlay, 0.3, result_img, 0.7, 0)

            cv2.rectangle(result_img, (left, top), (right, bottom), (255, 165, 0), 2)

    return result_img


if __name__ == "__main__":
    # 单元测试
    assert parse_number("85.5K") == 85.5
    assert parse_number("≤5mA") == 5.0
    assert parse_number("N/A") is None
    assert parse_int("123.45") == 123
    print("utils.py 单元测试通过")
