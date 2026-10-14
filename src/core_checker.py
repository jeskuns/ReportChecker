"""
核心校验引擎模块 — 多模式 PDF 识别 + 多引擎 OCR 级联

PDF 处理策略（按文档类型自动分流）：
  1. 文字型 PDF（可编辑） → PyMuPDF 直接提取文本（最快、最准）
  2. 图片型 PDF（扫描件） → OCR 级联链：
     a. PaddleOCR（paddlepaddle 后端，中文优化，首选）
     b. Tesseract OCR（便携版，deps/tesseract/，备选 #1）
     c. PaddleOCR + 增强预处理（二值化/降噪/锐化，备选 #2）

所有依赖均已本地化到项目 deps/ 和 models/ 目录，无需系统安装。
"""

import os
import re
import subprocess
import fitz
from typing import Optional, Dict, List, Any, Tuple
from PIL import Image, ImageDraw, ImageFont
import numpy as np
# cv2 延迟导入：仅在预处理引擎首次使用时才加载，避免启动时加载数百 MB 的 DLL

from utils import (
    parse_number,
    read_json_file,
    write_json_file,
    calculate_temperature_rise,
    check_tolerance,
    check_limit,
    format_error_message,
    find_number_regions,
    highlight_number_regions,
    draw_ocr_boxes,
)
from adobe_reader_renderer import AdobeReaderRenderer, find_adobe_reader
from adobe_window_capture import AdobeWindowCapture
from config import (
    TEMPLATES_DIR,
    RESULT_DIR,
    MODELS_DIR,
    DEFAULT_LIMITS,
    TOLERANCE,
    OCR_CONFIG,
)


# ───────────────── 项目本地依赖路径 ─────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPS_DIR = os.path.join(PROJECT_ROOT, 'deps')
TESSERACT_DIR = os.path.join(DEPS_DIR, 'tesseract')
TESSERACT_EXE = os.path.join(TESSERACT_DIR, 'tesseract.exe')
TESSDATA_DIR = os.path.join(TESSERACT_DIR, 'tessdata')

# ───────────────── OCR 模型统一存放目录（每个模型一个文件夹）─────────────────
# 结构：
#   models/ocr/paddle_det/   ← PaddleOCR 检测模型（inference.pdiparams 等）
#   models/ocr/paddle_rec/   ← PaddleOCR 识别模型
#   models/ocr/rapid/        ← RapidOCR 的 3 个 onnx 模型
OCR_MODEL_DIR = os.path.join(MODELS_DIR, 'ocr')
PADDLE_DET_DIR = os.path.join(OCR_MODEL_DIR, 'paddle_det')
PADDLE_REC_DIR = os.path.join(OCR_MODEL_DIR, 'paddle_rec')
RAPID_MODEL_DIR = os.path.join(OCR_MODEL_DIR, 'rapid')
EASYOCR_MODEL_DIR = os.path.join(OCR_MODEL_DIR, 'easyocr')

# ───────────────── PaddlePaddle 本地模型路径（必须在任何 PaddleX/PaddleOCR 导入前设置）─────────────────
os.environ['PADDLEOCR_HOME'] = OCR_MODEL_DIR
os.environ['PADDLE_PDX_CACHE_HOME'] = OCR_MODEL_DIR
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'


# =========================== OCR 引擎基类 ===========================

class BaseOCREngine:
    """OCR 引擎基类，定义统一接口"""
    
    def __init__(self, engine_name: str):
        self._engine_name = engine_name
        self._available = False
        self._error_message = ""
    
    def is_available(self) -> bool:
        return self._available
    
    def get_engine_name(self) -> str:
        return self._engine_name
    
    def get_error_message(self) -> str:
        return self._error_message
    
    def recognize_region(self, image: np.ndarray) -> Optional[str]:
        raise NotImplementedError
    
    def recognize_full_page(self, image: np.ndarray) -> Optional[str]:
        """识别整页图像（默认复用区域识别或逐块识别）"""
        return self.recognize_region(image)


# =========================== 引擎 1：PaddleOCR ===========================

class PaddleOCREngine(BaseOCREngine):
    """PaddleOCR 引擎（paddlepaddle 推理后端，中文优化首选）"""
    
    def __init__(self):
        super().__init__("PaddleOCR (paddle)")
        self._ocr = None
        self._init_engine()
    
    def _init_engine(self):
        try:
            from paddleocr import PaddleOCR
        except ImportError as e:
            self._available = False
            self._error_message = f"PaddleOCR 未安装: {e}"
            return

        # 仅在本地存在可用检测/识别模型时才实例化，避免触发联网下载（卡死）
        det_dir, rec_dir = self._find_local_models()
        if not det_dir or not rec_dir:
            self._available = False
            self._error_message = "PaddleOCR 本地模型缺失，将改用 Tesseract"
            return

        try:
            # 可选：方向分类模型目录（若存在）
            cls_dir = os.path.join(OCR_MODEL_DIR, 'paddle_cls')
            cls_kw = {'cls_model_dir': cls_dir} if os.path.isdir(cls_dir) else {}

            # paddleocr 3.x 不再支持 show_log 参数
            init_kwargs = dict(
                use_angle_cls=OCR_CONFIG.get('use_angle_cls', True),
                lang=OCR_CONFIG['lang'],
                det_model_dir=det_dir,
                rec_model_dir=rec_dir,
                **cls_kw,
            )
            try:
                self._ocr = PaddleOCR(**init_kwargs)
            except TypeError:
                # 降级：部分版本不支持 det_model_dir/rec_model_dir 关键字
                init_kwargs.pop('det_model_dir', None)
                init_kwargs.pop('rec_model_dir', None)
                init_kwargs.pop('cls_model_dir', None)
                self._ocr = PaddleOCR(**init_kwargs)
            self._available = True
            self._error_message = ""
            try:
                import paddleocr
                getattr(paddleocr, '__version__', 'unknown')
                self._engine_name = "PaddleOCR"
            except Exception:
                pass
        except Exception as e:
            self._available = False
            self._error_message = f"PaddleOCR 初始化失败: {e}"

    @staticmethod
    def _find_local_models():
        """返回固定的本地检测/识别模型目录（避免联网下载）

        统一路径：models/ocr/paddle_det, models/ocr/paddle_rec
        """
        det_dir = PADDLE_DET_DIR if os.path.isdir(PADDLE_DET_DIR) else None
        rec_dir = PADDLE_REC_DIR if os.path.isdir(PADDLE_REC_DIR) else None
        return det_dir, rec_dir
    
    def recognize_region(self, image: np.ndarray) -> Optional[str]:
        if not self.is_available() or self._ocr is None:
            return None

        try:
            result = self._ocr.ocr(image)

            if result and len(result) > 0:
                # PaddleOCR v3 返回格式可能有差异
                first = result[0] if isinstance(result, list) else result
                if not first:
                    return None

                # 收集 (y_top, text) 用于按行分组
                items = []

                if isinstance(first, list) and len(first) > 0:
                    for item in first:
                        if isinstance(item, list) and len(item) >= 2:
                            box = item[0]
                            text_info = item[1]
                            text = ''
                            if isinstance(text_info, (list, tuple)) and len(text_info) > 0:
                                text = text_info[0]
                            elif isinstance(text_info, str):
                                text = text_info
                            if isinstance(text, str) and text.strip():
                                y_top = 0
                                if isinstance(box, (list, tuple)) and len(box) >= 2:
                                    try:
                                        ys = [pt[1] if isinstance(pt, (list, tuple)) else 0 for pt in box]
                                        y_top = min(ys) if ys else 0
                                    except Exception:
                                        y_top = 0
                                items.append((y_top, text.strip()))

                # v3 dict 结构
                if isinstance(first, dict):
                    rec_texts = first.get('rec_texts', first.get('rec_text', first.get('texts', [])))
                    rec_scores = first.get('rec_scores', [])
                    polys = first.get('rec_polys', first.get('dt_polys', []))
                    if isinstance(rec_texts, list):
                        for i, text in enumerate(rec_texts):
                            if isinstance(text, str) and text.strip():
                                y_top = 0
                                if isinstance(polys, list) and i < len(polys):
                                    try:
                                        pts = polys[i]
                                        ys = [pt[1] if isinstance(pt, (list, tuple)) else 0 for pt in pts]
                                        y_top = min(ys) if ys else 0
                                    except Exception:
                                        y_top = 0
                                items.append((y_top, text.strip()))

                if not items:
                    return None

                # 按 y 坐标分组保留行结构
                items.sort(key=lambda x: x[0])
                lines = []
                current_line = []
                current_y = None
                y_threshold = 20  # 300DPI下行高更大，阈值设为20像素

                for y, text in items:
                    if current_y is None or abs(y - current_y) <= y_threshold:
                        current_line.append(text)
                        current_y = y if current_y is None else min(current_y, y)
                    else:
                        if current_line:
                            lines.append('  '.join(current_line))
                        current_line = [text]
                        current_y = y

                if current_line:
                    lines.append('  '.join(current_line))

                return '\n'.join(lines).strip() if lines else None

        except Exception:
            pass

        return None


# =========================== 引擎 2：Tesseract 便携版 ===========================

class TesseractOCREngine(BaseOCREngine):
    """Tesseract OCR 引擎（便携版，deps/tesseract/）"""
    
    def __init__(self):
        super().__init__("Tesseract (便携)")
        self._tesseract_exe = None
        self._available_langs = []
        self._init_engine()
    
    def _init_engine(self):
        try:
            import pytesseract
            
            # 检查本地 Tesseract 便携版
            if os.path.exists(TESSERACT_EXE):
                self._tesseract_exe = TESSERACT_EXE
                pytesseract.pytesseract.tesseract_cmd = self._tesseract_exe
                
                # 设置 tessdata 路径
                if os.path.exists(TESSDATA_DIR):
                    os.environ['TESSDATA_PREFIX'] = TESSDATA_DIR
                
                # 检测可用语言
                self._detect_available_langs()
                
                self._available = True
                self._error_message = ""
                
                # 更新引擎名（简写，去掉括号细节）
                self._engine_name = "Tesseract"
            else:
                # 尝试系统安装的 Tesseract
                try:
                    ver = pytesseract.get_tesseract_version()
                    self._available = True
                    self._engine_name = f"Tesseract v{ver} (系统)"
                    self._detect_available_langs()
                except Exception:
                    self._available = False
                    self._error_message = "Tesseract 便携版未找到，请将 tesseract.exe 放入 deps/tesseract/"
                    
        except ImportError:
            self._available = False
            self._error_message = "pytesseract 未安装"
        except Exception as e:
            self._available = False
            self._error_message = f"Tesseract 初始化失败: {e}"
    
    def _detect_available_langs(self):
        """检测可用语言包"""
        self._available_langs = []
        try:
            result = subprocess.run(
                [self._tesseract_exe, '--list-langs'],
                capture_output=True, text=True, timeout=10
            )
            # 过滤出实际的语言，跳过第一行 "List of available languages"
            langs = result.stdout.strip().split('\n')
            for lang in langs[1:]:
                lang = lang.strip()
                if lang and lang != 'osd':
                    self._available_langs.append(lang)
        except Exception:
            if os.path.exists(TESSDATA_DIR):
                for f in os.listdir(TESSDATA_DIR):
                    if f.endswith('.traineddata'):
                        lang = f.replace('.traineddata', '')
                        if lang != 'osd':
                            self._available_langs.append(lang)
    
    def _get_lang_param(self) -> str:
        """获取合适的语言参数"""
        chi_langs = [l for l in self._available_langs if 'chi' in l or 'zh' in l]
        eng_langs = [l for l in self._available_langs if l == 'eng']
        
        langs = []
        if chi_langs:
            langs.append(chi_langs[0])  # chi_sim 或 chi_tra
        if eng_langs:
            langs.append('eng')
        
        if not langs:
            langs = self._available_langs[:2]  # 取前两个可用语言
        if not langs:
            return 'eng'  # 默认
        
        return '+'.join(langs)
    
    def recognize_region(self, image: np.ndarray) -> Optional[str]:
        if not self.is_available():
            return None
        
        try:
            import pytesseract
            if self._tesseract_exe:
                pytesseract.pytesseract.tesseract_cmd = self._tesseract_exe
            
            img = Image.fromarray(image)
            lang = self._get_lang_param()
            
            # PSM 6: 将图像视为单一统一文本块
            text = pytesseract.image_to_string(img, lang=lang, config='--psm 6')
            result = text.strip()
            
            return result if result else None
            
        except Exception:
            pass
        
        return None


# =========================== 引擎 3：RapidOCR（ONNX 轻量） ===========================

class RapidOCREngine(BaseOCREngine):
    """
    RapidOCR 引擎（ONNXRuntime 后端，轻量中文 OCR）
    
    特点：
      - 不依赖 PyTorch/PaddlePaddle，体积更小
      - 纯 CPU 推理速度快
      - 中文识别精度优秀，适合报告扫描件
    """
    
    def __init__(self):
        super().__init__("RapidOCR (ONNX)")
        self._ocr = None
        self._init_engine()
    
    def _init_engine(self):
        try:
            from rapidocr_onnxruntime import RapidOCR

            # 使用统一存放的本地 onnx 模型（models/ocr/rapid/）
            det_path = os.path.join(RAPID_MODEL_DIR, 'ch_PP-OCRv4_det_infer.onnx')
            rec_path = os.path.join(RAPID_MODEL_DIR, 'ch_PP-OCRv4_rec_infer.onnx')
            cls_path = os.path.join(RAPID_MODEL_DIR, 'ch_ppocr_mobile_v2.0_cls_infer.onnx')

            kw = {}
            if os.path.exists(det_path):
                kw['det_model_path'] = det_path
            if os.path.exists(rec_path):
                kw['rec_model_path'] = rec_path
            if os.path.exists(cls_path):
                kw['cls_model_path'] = cls_path

            # 关闭冗余日志
            self._ocr = RapidOCR(
                use_det=True,
                use_cls=True,
                use_rec=True,
                verbose=False,
                **kw,
            )
            self._available = True
            self._error_message = ""

            try:
                import rapidocr_onnxruntime
                ver = getattr(rapidocr_onnxruntime, '__version__', 'unknown')
                self._engine_name = "RapidOCR"
            except Exception:
                pass

        except ImportError as e:
            self._available = False
            self._error_message = f"RapidOCR 未安装: {e}"
        except Exception as e:
            self._available = False
            self._error_message = f"RapidOCR 初始化失败: {e}"
    
    def recognize_region(self, image: np.ndarray) -> Optional[str]:
        if not self.is_available() or self._ocr is None:
            return None

        try:
            result = self._ocr(image)
            if not result or len(result) < 2 or not result[0]:
                return None

            # RapidOCR 返回格式: result[0] = [[box, text, score], ...]
            # 按 y 坐标分组，保留行结构（对表格识别至关重要）
            items = []
            for item in result[0]:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    box = item[0]
                    text = item[1]
                    if isinstance(text, str) and text.strip():
                        # box 是 [[x0,y0],[x1,y1],[x2,y2],[x3,y3]] 格式
                        y_top = 0
                        if isinstance(box, (list, tuple)) and len(box) >= 2:
                            try:
                                ys = [pt[1] if isinstance(pt, (list, tuple)) else 0 for pt in box]
                                y_top = min(ys) if ys else 0
                            except Exception:
                                y_top = 0
                        items.append((y_top, text.strip()))

            if not items:
                return None

            # 按 y 坐标排序，相近 y 归为同一行
            items.sort(key=lambda x: x[0])
            lines = []
            current_line = []
            current_y = None
            y_threshold = 20  # 300DPI下行高更大，阈值设为20像素

            for y, text in items:
                if current_y is None or abs(y - current_y) <= y_threshold:
                    current_line.append(text)
                    current_y = y if current_y is None else min(current_y, y)
                else:
                    # 新行
                    if current_line:
                        lines.append('  '.join(current_line))
                    current_line = [text]
                    current_y = y

            if current_line:
                lines.append('  '.join(current_line))

            return '\n'.join(lines).strip() if lines else None

        except Exception:
            pass

        return None


# =========================== 引擎 4：EasyOCR（可选） ===========================

class EasyOCREngine(BaseOCREngine):
    """
    EasyOCR 引擎（PyTorch 后端，多语言支持）
    
    注意：
      - 需要额外安装 easyocr（pip install easyocr）
      - 会显著增加打包体积（约数百 MB），默认不强制启用
      - 仅在用户自行安装后可用
    """
    
    def __init__(self, languages: List[str] = None):
        super().__init__("EasyOCR (可选)")
        self._languages = languages or ['ch_sim', 'en']
        self._ocr = None
        self._init_engine()
    
    def _init_engine(self):
        try:
            import easyocr
            # 使用本地模型目录，避免依赖用户目录或联网下载
            model_dir = EASYOCR_MODEL_DIR if os.path.isdir(EASYOCR_MODEL_DIR) else None
            self._ocr = easyocr.Reader(
                self._languages,
                gpu=False,
                verbose=False,
                model_storage_directory=model_dir,
            )
            self._available = True
            self._error_message = ""
            
            try:
                self._engine_name = "EasyOCR"
            except Exception:
                pass
            
        except ImportError:
            self._available = False
            self._error_message = "EasyOCR 未安装（pip install easyocr）"
        except Exception as e:
            self._available = False
            self._error_message = f"EasyOCR 初始化失败: {e}"
    
    def recognize_region(self, image: np.ndarray) -> Optional[str]:
        if not self.is_available() or self._ocr is None:
            return None

        try:
            result = self._ocr.readtext(image)
            if not result:
                return None

            # EasyOCR 返回: ([[x0,y0],[x1,y1],[x2,y2],[x3,y3]], text, confidence)
            # 按 y 坐标分组保留行结构
            items = []
            for item in result:
                if isinstance(item, (tuple, list)) and len(item) >= 2:
                    box = item[0]
                    text = item[1]
                    if isinstance(text, str) and text.strip():
                        y_top = 0
                        if isinstance(box, (list, tuple)) and len(box) >= 2:
                            try:
                                ys = [pt[1] if isinstance(pt, (list, tuple)) else 0 for pt in box]
                                y_top = min(ys) if ys else 0
                            except Exception:
                                y_top = 0
                        items.append((y_top, text.strip()))

            if not items:
                return None

            # 按 y 坐标分组
            items.sort(key=lambda x: x[0])
            lines = []
            current_line = []
            current_y = None
            y_threshold = 20  # 300DPI下行高更大，阈值设为20像素

            for y, text in items:
                if current_y is None or abs(y - current_y) <= y_threshold:
                    current_line.append(text)
                    current_y = y if current_y is None else min(current_y, y)
                else:
                    if current_line:
                        lines.append('  '.join(current_line))
                    current_line = [text]
                    current_y = y

            if current_line:
                lines.append('  '.join(current_line))

            return '\n'.join(lines).strip() if lines else None

        except Exception:
            pass

        return None


# =========================== 引擎 5：PaddleOCR + 增强预处理 ===========================

class PreprocessedPaddleOCREngine(BaseOCREngine):
    """
    PaddleOCR + OpenCV 增强预处理引擎
    
    在 OCR 之前对图像进行自动增强（二值化、降噪、锐化、对比度增强），
    专门处理低对比度、噪声多的扫描件，与直出 PaddleOCR 形成有效的差异化备选。
    """
    
    def __init__(self, paddle_engine: PaddleOCREngine = None):
        super().__init__("PaddleOCR + 增强预处理")
        self._paddle = paddle_engine
    
    def is_available(self) -> bool:
        return self._paddle is not None and self._paddle.is_available()
    
    def get_error_message(self) -> str:
        if self._paddle is None:
            return "未绑定 PaddleOCR 实例"
        return self._paddle.get_error_message()
    
    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """
        多策略图像增强，依次尝试多种预处理方法，选择最可能提高识别率的
        
        策略：
        1. 自适应直方图均衡化 (CLAHE) + USM 锐化
        2. Otsu 二值化
        3. 自适应阈值二值化
        4. 对比度拉伸（1%~99% 百分位）
        """
        import cv2  # 延迟导入
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if len(image.shape) == 3 else image
        
        # 策略1：CLAHE + 锐化 → RGB
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        # USM 锐化
        blurred = cv2.GaussianBlur(enhanced, (0, 0), 3)
        sharpened = cv2.addWeighted(enhanced, 1.5, blurred, -0.5, 0)
        
        strategy1 = cv2.cvtColor(sharpened, cv2.COLOR_GRAY2RGB)
        
        # 策略2：Otsu 二值化
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        strategy2 = cv2.cvtColor(otsu, cv2.COLOR_GRAY2RGB)
        
        # 策略3：自适应阈值
        adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 15, 4
        )
        strategy3 = cv2.cvtColor(adaptive, cv2.COLOR_GRAY2RGB)
        
        # 返回多张图组成的试验组：依次尝试，首个有结果即返回
        # 实际使用时会存储策略并在 recognize_region 中依次尝试
        return [strategy1, strategy2, strategy3]
    
    def recognize_region(self, image: np.ndarray) -> Optional[str]:
        if not self.is_available():
            return None
        
        try:
            # 生成增强图像序列
            enhanced_images = self._preprocess(image)
            
            # 依次尝试各策略
            for idx, enhanced in enumerate(enhanced_images):
                try:
                    result = self._paddle.recognize_region(enhanced)
                    if result:
                        self._engine_name = "增强预处理"
                        return result
                except Exception:
                    continue
            
        except Exception:
            pass
        
        return None


# =========================== 多引擎级联协调器 ===========================

class MultiOCREngine(BaseOCREngine):
    """
    多引擎自动级联 OCR
    
    引擎优先级（按实际测试效果与体积综合排列）：
      1. PaddleOCR              — 首选，中文 OCR 精度最高
      2. RapidOCR (ONNX)        — 轻量备选，不依赖 PyTorch
      3. Tesseract OCR          — 传统 OCR，多语言支持
      4. EasyOCR                — 可选引擎（需用户自行安装）
      5. PaddleOCR + 增强预处理 — 兜底，专门处理低质量扫描件
    
    级联逻辑：上一级引擎返回 None 时自动切换到下一级
    """
    
    def __init__(self):
        super().__init__("多引擎级联 OCR")
        # 懒初始化：构造时不实际加载任何 OCR 模型（避免打开文件即卡死/崩溃）
        # 仅登记引擎工厂，首次 recognize_region 时才按需逐个初始化
        #
        # 级联顺序（重要）：
        #   1. RapidOCR   — ONNX 本地模型，含中英文数字字库，无需联网下载，速度快 → 首选
        #   2. Tesseract  — 便携版本地 chi_sim+eng 字库，无需联网 → 备选
        #   3. PaddleOCR  — 精度高但首次可能联网下载模型，放到本地引擎之后，避免卡死
        #   4. EasyOCR    — 可选
        #   5. 增强预处理 — 依赖 PaddleOCR，兜底
        self._engine_factories: List[tuple] = [
            ("RapidOCR", RapidOCREngine),
            ("EasyOCR", EasyOCREngine),
            ("Tesseract", TesseractOCREngine),
            ("PaddleOCR", PaddleOCREngine),
            ("增强预处理", None),  # 占位，依赖 PaddleOCR 实例化后补充
        ]
        self._engines: List[BaseOCREngine] = []
        self._pending_names: List[str] = []  # 尚未实例化的重引擎名（PaddleOCR/增强预处理）
        self._factory_map = {name: fac for name, fac in self._engine_factories if fac is not None}
        self._current_engine: Optional[BaseOCREngine] = None
        self._engine_stats: Dict[str, int] = {}  # 各引擎成功次数
        self._initialized = False
        self._available = False  # 直到首次初始化才确定

    def _ensure_initialized(self):
        """首次真正需要 OCR 时才初始化引擎（懒加载，加速启动、避免崩溃）

        关键优化：只实例化『本地轻量引擎』（RapidOCR / Tesseract / EasyOCR），
        它们无需联网、启动快。PaddleOCR 与『增强预处理』推迟到级联真正轮到它们
        时才按需实例化，避免在打开/校验文字型文档时就被迫联网下载 PaddleOCR 模型。
        """
        if self._initialized:
            return
        self._initialized = True

        # 本地轻量引擎优先实例化；重引擎(PaddleOCR/增强预处理)延迟实例化
        _heavy = {"PaddleOCR", "增强预处理"}

        paddle_ref = None
        for name, factory in self._engine_factories:
            if factory is None:
                # 增强预处理依赖 PaddleOCR，仅在其可用时追加（延迟到级联时处理）
                continue
            if name in _heavy:
                # 推迟实例化，记录到待定列表，级联轮到时再 factory()
                self._pending_names.append(name)
                continue
            try:
                engine = factory()
            except Exception:
                continue
            self._engines.append(engine)
            if name == "PaddleOCR" and engine.is_available():
                paddle_ref = engine
            if engine.is_available() and self._current_engine is None:
                self._current_engine = engine
                self._available = True

        if not self._available:
            # 本地引擎都不可用，但可能还有 PaddleOCR 待定；标记为可用待定，
            # 级联时会尝试 PaddleOCR
            self._error_message = "本地引擎暂不可用，将尝试 PaddleOCR"
        else:
            self._error_message = f"主引擎: {self._current_engine.get_engine_name()}"

    def get_engine_info(self) -> str:
        """获取所有引擎状态信息"""
        self._ensure_initialized()
        info = []
        for engine in self._engines:
            status = "✓" if engine.is_available() else "✗"
            info.append(f"{status} {engine.get_engine_name()}: {engine.get_error_message() or '就绪'}")
        return "\n".join(info)

    def can_be_available(self) -> bool:
        """
        轻量预检：不加载任何模型，仅判断是否存在任一引擎的安装基础
        （依赖包目录存在 / 可执行文件存在 / 模型文件齐全）。
        用于在打开文件时判断 OCR 是否"可能可用"，
        避免为判断可用性而强制 import 重模块（甚至联网下载）模型导致卡顿。
        """
        # 已初始化则直接用真实状态
        if self._initialized:
            return self._available
    
        # RapidOCR：检查 onnx 模型文件是否齐全（不 import，仅查文件系统）
        try:
            if os.path.isdir(RAPID_MODEL_DIR):
                onnx_files = [f for f in os.listdir(RAPID_MODEL_DIR) if f.endswith('.onnx')]
                if len(onnx_files) >= 2:
                    # 再确认 rapidocr_onnxruntime 包可找到（不实际 import）
                    import importlib.util
                    if importlib.util.find_spec("rapidocr_onnxruntime") is not None:
                        return True
        except Exception:
            pass
    
        # Tesseract 便携版：检查可执行文件 + tessdata 目录
        if os.path.exists(TESSERACT_EXE) and os.path.isdir(TESSDATA_DIR):
            return True
    
        # PaddleOCR：检查包可找到 + 本地 det/rec 模型目录存在
        try:
            import importlib.util
            if importlib.util.find_spec("paddleocr") is not None:
                if os.path.isdir(PADDLE_DET_DIR) and os.path.isdir(PADDLE_REC_DIR):
                    return True
        except Exception:
            pass
    
        # EasyOCR：检查包目录是否存在（不 import，import 非常慢）
        try:
            import importlib.util
            if importlib.util.find_spec("easyocr") is not None:
                return True
        except Exception:
            pass
    
        return False

    def get_engine_list(self) -> List[Dict[str, Any]]:
        """
        返回所有引擎的元信息（名称、是否可用、诊断详情），供 GUI 渲染标签。
        为了不阻塞 UI，使用轻量文件系统检查 + importlib.util.find_spec 代替实际 import。
        """
        result = []
        for name, _ in self._engine_factories:
            info = {"name": name, "available": False, "detail": ""}
            if name == "PaddleOCR":
                ok, detail = self._check_paddleocr_detail()
                info["available"] = ok
                info["detail"] = detail
            elif name == "RapidOCR":
                ok, detail = self._check_rapid_detail()
                info["available"] = ok
                info["detail"] = detail
            elif name == "Tesseract":
                ok, detail = self._check_tesseract_detail()
                info["available"] = ok
                info["detail"] = detail
            elif name == "EasyOCR":
                try:
                    import importlib.util
                    spec = importlib.util.find_spec("easyocr")
                    if spec is None:
                        info["available"] = False
                        info["detail"] = "未安装 easyocr 包"
                    else:
                        # 检查本地模型文件
                        has_models = (
                            os.path.isdir(EASYOCR_MODEL_DIR) and
                            any(f.endswith('.pth') for f in os.listdir(EASYOCR_MODEL_DIR))
                        )
                        model_info = "本地模型齐全" if has_models else "本地模型缺失"
                        # 检查引擎是否已初始化
                        if self._initialized:
                            easy_engine = next(
                                (e for e in self._engines if "EasyOCR" in e.get_engine_name()),
                                None
                            )
                            if easy_engine and easy_engine.is_available():
                                info["available"] = True
                                info["detail"] = f"已加载，{model_info}"
                            else:
                                info["available"] = False
                                info["detail"] = f"引擎初始化失败，{model_info}"
                        else:
                            info["available"] = has_models
                            info["detail"] = f"包已安装，{model_info}，首次使用时加载"
                except Exception as e:
                    info["detail"] = f"检测异常: {e}"
            elif name == "增强预处理":
                ok, detail = self._check_paddleocr_detail()
                info["available"] = ok
                info["detail"] = detail
            result.append(info)
        return result

    @staticmethod
    def _check_rapid_detail() -> Tuple[bool, str]:
        """RapidOCR 详细检测：包 + onnx 模型文件"""
        import importlib.util
        spec = importlib.util.find_spec("rapidocr_onnxruntime")
        if spec is None:
            return False, "未安装 rapidocr_onnxruntime 包"
        if not os.path.isdir(RAPID_MODEL_DIR):
            return False, f"模型目录不存在: {RAPID_MODEL_DIR}"
        onnx_files = [f for f in os.listdir(RAPID_MODEL_DIR) if f.endswith('.onnx')]
        if len(onnx_files) < 2:
            return False, f"ONNX 模型文件不足（{len(onnx_files)}/2）"
        return True, f"模型齐全（{len(onnx_files)} 个 ONNX 文件）"

    @staticmethod
    def _check_tesseract_detail() -> Tuple[bool, str]:
        """Tesseract 详细检测：exe + tessdata"""
        if not os.path.exists(TESSERACT_EXE):
            return False, f"tesseract.exe 不存在: {TESSERACT_EXE}"
        if not os.path.isdir(TESSDATA_DIR):
            return False, f"tessdata 目录不存在: {TESSDATA_DIR}"
        # 检查是否有语言数据
        lang_files = [f for f in os.listdir(TESSDATA_DIR) if f.endswith('.traineddata')]
        if not lang_files:
            return False, "tessdata 中无语言文件"
        return True, f"语言包: {', '.join(lang_files)}"

    @staticmethod
    def _check_paddleocr_detail() -> Tuple[bool, str]:
        """PaddleOCR 详细检测：paddlepaddle + paddleocr 包 + det/rec 模型"""
        import importlib.util
        # 检查 paddlepaddle 推理后端
        paddle_spec = importlib.util.find_spec("paddle")
        if paddle_spec is None:
            return False, "未安装 paddlepaddle 包"
        spec = importlib.util.find_spec("paddleocr")
        if spec is None:
            return False, "未安装 paddleocr 包"
        det_ok = os.path.isdir(PADDLE_DET_DIR)
        rec_ok = os.path.isdir(PADDLE_REC_DIR)
        if not det_ok and not rec_ok:
            return False, "det/rec 模型目录均不存在"
        if not det_ok:
            return False, f"det 模型目录不存在: {PADDLE_DET_DIR}"
        if not rec_ok:
            return False, f"rec 模型目录不存在: {PADDLE_REC_DIR}"
        return True, "paddlepaddle + det/rec 模型就绪"

    def get_current_engine_name(self) -> str:
        if self._current_engine:
            return self._current_engine.get_engine_name()
        return "无"

    def set_forced_engine(self, engine_name: str) -> bool:
        """强制指定使用某个引擎（手动模式）

        Args:
            engine_name: 引擎名（如 "RapidOCR"/"Tesseract"/"PaddleOCR"/"EasyOCR"），
                         传空字符串或 "自动" 恢复级联模式

        Returns:
            True 如果切换成功
        """
        if not engine_name or engine_name == "自动":
            self._forced_engine_name = None
            return True

        self._ensure_initialized()
        self._forced_engine_name = engine_name

        # 尝试找到对应引擎并设为当前引擎
        # 先在已初始化的引擎中找
        for engine in self._engines:
            if engine_name in engine.get_engine_name():
                if engine.is_available():
                    self._current_engine = engine
                    return True

        # 重引擎（PaddleOCR/增强预处理）可能尚未实例化
        if engine_name in self._pending_names:
            factory = self._factory_map.get(engine_name)
            if factory:
                try:
                    engine = factory()
                    self._engines.append(engine)
                    self._pending_names.remove(engine_name)
                    if engine.is_available():
                        self._current_engine = engine
                        return True
                except Exception:
                    pass

        return False

    @property
    def forced_engine_name(self) -> Optional[str]:
        return getattr(self, '_forced_engine_name', None)

    def recognize_region(self, image: np.ndarray,
                         on_engine_try: Optional[callable] = None,
                         on_engine_result: Optional[callable] = None) -> Optional[str]:
        """
        级联识别：依次尝试各引擎直到成功。首次调用会按需初始化引擎。

        Args:
            image: 输入图像
            on_engine_try: 回调(name, available)，在进入某个引擎前触发（用于高亮标签）
            on_engine_result: 回调(name, success)，在引擎返回后触发

        Returns:
            识别文本；全部失败返回 None
        """
        self._ensure_initialized()
        if not self._available:
            return None

        # 手动模式：强制使用指定引擎，不级联
        forced = getattr(self, '_forced_engine_name', None)
        if forced:
            for engine in self._engines:
                if forced in engine.get_engine_name() and engine.is_available():
                    name = engine.get_engine_name()
                    if on_engine_try:
                        try:
                            on_engine_try(name, True)
                        except Exception:
                            pass
                    try:
                        result = engine.recognize_region(image)
                        if result:
                            self._engine_stats[name] = self._engine_stats.get(name, 0) + 1
                            if on_engine_result:
                                try:
                                    on_engine_result(name, True)
                                except Exception:
                                    pass
                            return result
                    except Exception:
                        pass
                    if on_engine_result:
                        try:
                            on_engine_result(name, False)
                        except Exception:
                            pass
                    return None
            return None  # 强制引擎不可用

        # 自动模式：优先使用已确定的当前引擎
        # 若每次都从头级联所有引擎会非常慢。先用当前引擎（命中率最高），
        # 仅在其失败时再完整级联兜底。
        tried = set()
        prefered = self._current_engine
        if prefered is not None and prefered.is_available():
            name = prefered.get_engine_name()
            tried.add(id(prefered))
            if on_engine_try:
                try:
                    on_engine_try(name, True)
                except Exception:
                    pass
            try:
                result = prefered.recognize_region(image)
                if result:
                    self._engine_stats[name] = self._engine_stats.get(name, 0) + 1
                    if on_engine_result:
                        try:
                            on_engine_result(name, True)
                        except Exception:
                            pass
                    return result
            except Exception:
                pass
            if on_engine_result:
                try:
                    on_engine_result(name, False)
                except Exception:
                    pass

        # 兜底：完整级联其余引擎（含按需实例化的重引擎 PaddleOCR / 增强预处理）
        # 用索引迭代，便于在遍历过程中动态追加“增强预处理”引擎
        idx = 0
        while idx < len(self._engines):
            engine = self._engines[idx]
            idx += 1
            if id(engine) in tried:
                continue
            name = engine.get_engine_name()

            # 增强预处理：依赖 PaddleOCR，仅当其可用时才在此处实例化追加一次
            if name == "增强预处理" and not engine.is_available():
                paddle = next((e for e in self._engines
                               if e.get_engine_name() == "PaddleOCR" and e.is_available()), None)
                if paddle is not None:
                    try:
                        new_enh = PreprocessedPaddleOCREngine(paddle)
                        if new_enh.is_available():
                            self._engines.append(new_enh)
                            engine = new_enh
                            name = engine.get_engine_name()
                    except Exception:
                        pass

            # 尚未实例化的重引擎（PaddleOCR）：按需 factory() 实例化
            if not engine.is_available() and name in self._factory_map:
                factory = self._factory_map.get(name)
                if factory is not None:
                    try:
                        engine = factory()
                        for j, e in enumerate(self._engines):
                            if e.get_engine_name() == name:
                                self._engines[j] = engine
                                break
                        name = engine.get_engine_name()
                    except Exception:
                        # 实例化失败（如 PaddleOCR 联网下载失败）→ 跳过重试，不阻塞
                        if on_engine_result:
                            try:
                                on_engine_result(name, False)
                            except Exception:
                                pass
                        continue
            if on_engine_try:
                try:
                    on_engine_try(name, engine.is_available())
                except Exception:
                    pass

            if not engine.is_available():
                if on_engine_result:
                    try:
                        on_engine_result(name, False)
                    except Exception:
                        pass
                continue

            try:
                result = engine.recognize_region(image)
                ok = bool(result)
                if ok:
                    self._engine_stats[name] = self._engine_stats.get(name, 0) + 1
                    if self._current_engine != engine:
                        switched_from = self._current_engine.get_engine_name() if self._current_engine else "无"
                        self._current_engine = engine
                        self._error_message = (
                            f"已从 {switched_from} 切换到 {engine.get_engine_name()}"
                        )
                    if on_engine_result:
                        try:
                            on_engine_result(name, True)
                        except Exception:
                            pass
                    return result
                else:
                    if on_engine_result:
                        try:
                            on_engine_result(name, False)
                        except Exception:
                            pass
            except Exception:
                if on_engine_result:
                    try:
                        on_engine_result(name, False)
                    except Exception:
                        pass
                continue

        return None

    def recognize_region_all_engines(self, image: np.ndarray,
                                     on_engine_try: Optional[callable] = None,
                                     on_engine_result: Optional[callable] = None
                                     ) -> list:
        """
        自动质量保障模式：依次用每个引擎单独识别，返回所有结果。

        与 recognize_region 的区别：不级联、不短路——每个引擎独立识别，
        由调用方根据填入率选最佳结果。

        Returns:
            [(engine_name, text), ...] 每个可用引擎一个结果
        """
        self._ensure_initialized()
        if not self._available:
            return []

        results = []
        tried_names = set()

        for engine in self._engines:
            name = engine.get_engine_name()

            # 增强预处理：依赖 PaddleOCR，按需实例化
            if name == "增强预处理" and not engine.is_available():
                paddle = next((e for e in self._engines
                               if e.get_engine_name() == "PaddleOCR" and e.is_available()), None)
                if paddle is not None:
                    try:
                        new_enh = PreprocessedPaddleOCREngine(paddle)
                        if new_enh.is_available():
                            self._engines.append(new_enh)
                            engine = new_enh
                            name = engine.get_engine_name()
                    except Exception:
                        pass

            # 尚未实例化的重引擎按需加载
            if not engine.is_available() and name in self._factory_map:
                factory = self._factory_map.get(name)
                if factory is not None:
                    try:
                        engine = factory()
                        for j, e in enumerate(self._engines):
                            if e.get_engine_name() == name:
                                self._engines[j] = engine
                                break
                        name = engine.get_engine_name()
                    except Exception:
                        continue

            if not engine.is_available():
                continue
            if name in tried_names:
                continue
            tried_names.add(name)

            if on_engine_try:
                try:
                    on_engine_try(name, True)
                except Exception:
                    pass

            try:
                text = engine.recognize_region(image)
                if text:
                    results.append((name, text))
                    if on_engine_result:
                        try:
                            on_engine_result(name, True)
                        except Exception:
                            pass
                else:
                    if on_engine_result:
                        try:
                            on_engine_result(name, False)
                        except Exception:
                            pass
            except Exception:
                if on_engine_result:
                    try:
                        on_engine_result(name, False)
                    except Exception:
                        pass

        return results

    def recognize_region_cross_verify(self, image: np.ndarray,
                                       on_progress: Optional[callable] = None
                                       ) -> Dict[str, Any]:
        """多引擎交叉比对识别

        让所有可用引擎分别识别同一张图，返回各引擎结果和交叉比对结论。

        Returns:
            {
                'results': {engine_name: text},
                'best_text': str,           # 交叉比对后最佳文本
                'agreement': float,          # 一致性 0~1
                'used_engines': [str],      # 参与的引擎名列表
            }
        """
        self._ensure_initialized()
        results = {}

        # 收集所有可用引擎
        engines_to_try = []
        for engine in self._engines:
            if engine.is_available():
                engines_to_try.append(engine)

        # 按需实例化重引擎
        for name in list(self._pending_names):
            factory = self._factory_map.get(name)
            if factory:
                try:
                    engine = factory()
                    self._engines.append(engine)
                    self._pending_names.discard(name)
                    if engine.is_available():
                        engines_to_try.append(engine)
                except Exception:
                    pass

        for i, engine in enumerate(engines_to_try):
            name = engine.get_engine_name()
            if on_progress:
                try:
                    on_progress(name, i + 1, len(engines_to_try))
                except Exception:
                    pass
            try:
                text = engine.recognize_region(image)
                if text:
                    results[name] = text
            except Exception:
                pass

        # 交叉比对：选择被最多引擎认同的结果
        best_text = self._cross_verify_best(results)
        agreement = self._calculate_agreement(results)

        return {
            'results': results,
            'best_text': best_text,
            'agreement': agreement,
            'used_engines': list(results.keys()),
        }

    @staticmethod
    def _cross_verify_best(results: Dict[str, str]) -> str:
        """从多引擎结果中选出最佳文本

        策略：把每个引擎结果按行分割，统计哪些行被多个引擎共同识别，
        被多数引擎认同的行优先保留。
        """
        if not results:
            return ""
        if len(results) == 1:
            return list(results.values())[0]

        # 按引擎数量取最长的结果（简单策略）
        # 更复杂策略：逐行投票
        engine_names = list(results.keys())
        all_texts = list(results.values())

        # 按行分割每个引擎的结果
        line_votes = {}  # normalized_line -> [engine_count, best_line]
        for eng_name, text in results.items():
            for line in text.split('\n'):
                stripped = line.strip()
                if not stripped:
                    continue
                # 用数字序列作为行的指纹（忽略文字差异，只看数字）
                nums = tuple(re.findall(r'[-+]?\d+(?:\.\d+)?', stripped))
                if nums:
                    key = nums
                else:
                    key = stripped[:20]

                if key not in line_votes:
                    line_votes[key] = [0, stripped]
                line_votes[key][0] += 1
                # 保留最长版本
                if len(stripped) > len(line_votes[key][1]):
                    line_votes[key][1] = stripped

        # 按原始行顺序输出被多数引擎认同的行
        # 先用第一个引擎的行顺序作为参考
        ref_text = all_texts[0]
        output_lines = []
        used_keys = set()

        for line in ref_text.split('\n'):
            stripped = line.strip()
            if not stripped:
                continue
            nums = tuple(re.findall(r'[-+]?\d+(?:\.\d+)?', stripped))
            key = nums if nums else stripped[:20]
            if key in line_votes:
                votes, best = line_votes[key]
                if key not in used_keys:
                    output_lines.append(best)
                    used_keys.add(key)

        # 补上其他引擎有但参考引擎没有的行
        for key, (votes, best) in line_votes.items():
            if key not in used_keys and votes >= 2:
                output_lines.append(best)
                used_keys.add(key)

        return '\n'.join(output_lines) if output_lines else all_texts[0]

    @staticmethod
    def _calculate_agreement(results: Dict[str, str]) -> float:
        """计算多引擎结果一致性 0~1"""
        if len(results) <= 1:
            return 1.0
        texts = list(results.values())
        # 比较数字提取结果的一致性
        all_nums = []
        for t in texts:
            nums = re.findall(r'[-+]?\d+(?:\.\d+)?', t)
            all_nums.append(set(nums))
        if not all_nums or not all_nums[0]:
            return 0.0
        # 取交集占比
        common = all_nums[0]
        for s in all_nums[1:]:
            common = common & s
        total = all_nums[0]
        for s in all_nums[1:]:
            total = total | s
        return len(common) / len(total) if total else 0.0

class PDFTypeDetector:
    """
    PDF 文档类型检测器
    
    判断 PDF 是文字型（可编辑/可提取文本）还是图片型（扫描件）
    支持混合型判断（部分页文字型、部分页图片型）
    """
    
    @staticmethod
    def detect(doc: fitz.Document) -> Dict[str, Any]:
        """
        检测 PDF 类型
        
        Returns:
            {
                'is_text_based': bool,      # 整体是否为文字型
                'page_types': List[str],     # 每页类型: 'text' | 'image' | 'mixed'
                'text_page_count': int,      # 文字型页数
                'image_page_count': int,     # 图片型页数
                'total_text_chars': int,     # 总可提取字符数
                'confidence': float,         # 置信度 0-1
            }
        """
        text_page_count = 0
        image_page_count = 0
        page_types = []
        total_chars = 0
        
        for page in doc:
            try:
                text = page.get_text()
                char_count = len(text.strip())
                total_chars += char_count
                
                # 页面上图片数量
                images = page.get_images()
                has_images = len(images) > 0
                
                if char_count > 20:
                    text_page_count += 1
                    if has_images and char_count < 200:
                        page_types.append('mixed')
                    else:
                        page_types.append('text')
                else:
                    image_page_count += 1
                    page_types.append('image')
                    
            except Exception:
                image_page_count += 1
                page_types.append('image')
        
        total_pages = len(page_types)
        is_text_based = text_page_count >= image_page_count if total_pages > 0 else False
        
        # 置信度：文字页占比
        confidence = text_page_count / total_pages if total_pages > 0 else 0.0
        
        return {
            'is_text_based': is_text_based,
            'page_types': page_types,
            'text_page_count': text_page_count,
            'image_page_count': image_page_count,
            'total_text_chars': total_chars,
            'confidence': confidence,
        }


# =========================== PDF 渲染器 ===========================

class DocumentLoader:
    """通用文档加载器，支持 PDF、Word 和图片"""
    
    # 支持的图片格式
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.gif', '.webp'}
    WORD_EXTENSIONS = {'.docx', '.doc'}
    PDF_EXTENSIONS = {'.pdf'}
    
    def __init__(self):
        self._doc = None
        self._doc_type = None  # 'pdf' | 'word' | 'image' | 'adobe_image_pdf' | 'adobe_live'
        self._file_path = ""
        # Word 专用缓存
        self._word_text = ""
        self._word_paragraphs = []
        # 图片专用缓存
        self._image_array = None
        self._image_page_count = 1
        # 亿赛通 DLP 绕过：Adobe Reader 渲染出的图片缓存
        self._adobe_images = []  # List[str]
        self._adobe_renderer = None  # Optional[AdobeReaderRenderer]
        self._adobe_dpi = 200
        # 实时窗口捕获模式
        self._adobe_live_capture = None  # Optional[AdobeWindowCapture]

    def _is_adobe_mode(self) -> bool:
        """当前是否通过 Adobe Reader 渲染的图片模式工作。"""
        return self._doc_type in ('adobe_image_pdf', 'adobe_live') or bool(self._adobe_images)
    
    def open_pdf_from_adobe_window(self) -> bool:
        """从已打开的 Adobe Acrobat 窗口捕获 PDF（不打开文件）。

        用户需先手动在 Adobe Acrobat 中打开目标 PDF，
        本方法连接到已运行的 Acrobat 实例，自动翻到第 2 页并只截取该页。
        """
        try:
            if self._adobe_live_capture is None:
                self._adobe_live_capture = AdobeWindowCapture()
            if not self._adobe_live_capture.connect():
                return False

            page_count = self._adobe_live_capture.page_count
            import tempfile
            tmp_dir = tempfile.mkdtemp(prefix='reportchecker_live_')

            if page_count <= 0 or page_count == 999:
                # COM 无法获取页数，仅截取当前页
                out_path = os.path.join(tmp_dir, 'page_0001.png')
                if self._adobe_live_capture.capture_current_page_save(out_path):
                    self._adobe_images = [out_path]
                    self._doc_type = 'adobe_live'
                    self._image_page_count = 1
                    self._doc = None
                    return True
                return False

            # 直接翻到第 2 页（索引 1），只截取该页，不滚动整个文档
            target_page = min(1, page_count - 1)  # 第 2 页（测试结果页）
            if target_page < 0:
                target_page = 0
            self._adobe_live_capture.goto_page(target_page)

            out_path = os.path.join(tmp_dir, f'page_{target_page + 1:04d}.png')
            if self._adobe_live_capture.capture_current_page_save(out_path):
                self._adobe_images = [out_path]
                self._doc_type = 'adobe_live'
                self._image_page_count = 1
                self._doc = None
                return True
            return False
        except Exception as e:
            print(f'[Adobe live capture failed] {e}')
            return False

    def _open_pdf(self, file_path: str) -> bool:
        """打开 PDF：先尝试 PyMuPDF 直接读取；失败或被 DLP 拦截时，
        自动降级为 Adobe Reader 渲染图片模式 → 实时窗口捕获模式。"""
        # 1. 正常尝试 fitz 打开
        try:
            self._doc = fitz.open(file_path)
            self._doc_type = 'pdf'
            # 亿赛通可能不抛异常但返回空文档（0页）
            if self._doc and self._doc.page_count > 0:
                return True
            # 空文档，继续尝试 Adobe Reader 降级
            try:
                self._doc.close()
            except Exception:
                pass
            self._doc = None
        except Exception:
            pass

        # 2. 尝试 Adobe Reader 绕过
        try:
            if find_adobe_reader() is not None:
                if self._adobe_renderer is None:
                    self._adobe_renderer = AdobeReaderRenderer()
                if self._adobe_renderer.is_available():
                    import tempfile
                    tmp_dir = tempfile.mkdtemp(prefix='reportchecker_adobe_')
                    images = self._adobe_renderer.render_pdf_to_images(
                        file_path, dpi=self._adobe_dpi, output_dir=tmp_dir)
                    if images:
                        self._adobe_images = images
                        self._doc_type = 'adobe_image_pdf'
                        self._image_page_count = len(images)
                        self._doc = None
                        return True
        except Exception as adobe_err:
            print(f'[Adobe Reader fallback failed] {adobe_err}')

        # 3. 最终降级：实时窗口捕获（不需要打开文件）
        try:
            if self._adobe_live_capture is None:
                self._adobe_live_capture = AdobeWindowCapture()
            if self._adobe_live_capture.is_available():
                print('[DocumentLoader] 尝试从已打开的 Adobe Acrobat 窗口捕获...')
                if self.open_pdf_from_adobe_window():
                    return True
        except Exception as e:
            print(f'[Adobe live capture fallback failed] {e}')

        return False

    
    def _open_word(self, file_path: str) -> bool:
        try:
            from docx import Document
            doc = Document(file_path)
            self._word_paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            self._word_text = '\n'.join(self._word_paragraphs)
            self._doc = {'type': 'word', 'paragraphs': self._word_paragraphs}
            self._doc_type = 'word'
            self._image_page_count = 1
            return True
        except Exception:
            return False
    
    def _open_image(self, file_path: str) -> bool:
        try:
            img = Image.open(file_path).convert('RGB')
            self._image_array = np.array(img)
            self._doc = {'type': 'image', 'image': self._image_array}
            self._doc_type = 'image'
            self._image_page_count = 1
            return True
        except Exception:
            return False

    def open_document(self, file_path: str) -> bool:
        """通用文档打开接口：根据扩展名自动分发到 PDF / Word / 图片加载器。"""
        self.close_document()
        self._file_path = file_path
        ext = os.path.splitext(file_path.lower())[1]
        if ext in self.PDF_EXTENSIONS:
            return self._open_pdf(file_path)
        if ext in self.WORD_EXTENSIONS:
            return self._open_word(file_path)
        if ext in self.IMAGE_EXTENSIONS:
            return self._open_image(file_path)
        return False

    def open_pdf(self, file_path: str) -> bool:
        """兼容旧接口"""
        return self.open_document(file_path)

    def close_document(self):
        if self._doc_type == 'pdf' and self._doc:
            try:
                self._doc.close()
            except Exception:
                pass
        # 断开 Adobe 窗口捕获连接
        if self._adobe_live_capture is not None:
            try:
                self._adobe_live_capture.disconnect()
            except Exception:
                pass
            self._adobe_live_capture = None
        self._doc = None
        self._doc_type = None
        self._word_text = ""
        self._word_paragraphs = []
        self._image_array = None
        self._adobe_images = []
        self._adobe_renderer = None


    
    def close_pdf(self):
        """兼容旧接口"""
        self.close_document()
    
    def get_document_type(self) -> str:
        return self._doc_type or 'unknown'
    
    def get_page_count(self) -> int:
        if self._doc_type in ('pdf', 'adobe_image_pdf', 'adobe_live'):
            if self._doc_type in ('adobe_image_pdf', 'adobe_live'):
                return self._image_page_count
            return self._doc.page_count if self._doc else 0
        return self._image_page_count

    def is_text_based_pdf(self) -> bool:
        """文字型文档判断（图片型 / Adobe 渲染模式 / 窗口捕获模式返回 False）"""
        if self._doc_type in ('adobe_image_pdf', 'adobe_live'):
            return False
        if self._doc_type == 'pdf':
            try:
                for page in self._doc:
                    if page.get_text().strip():
                        return True
            except Exception:
                pass
        elif self._doc_type == 'word':
            return bool(self._word_text.strip())
        return False

    
    def detect_pdf_type(self) -> Dict[str, Any]:
        """兼容旧接口，统一返回文档类型信息"""
        if self._doc_type in ('adobe_image_pdf', 'adobe_live'):
            return {
                'is_text_based': False,
                'page_types': ['image'] * self._image_page_count,
                'text_page_count': 0,
                'image_page_count': self._image_page_count,
                'total_text_chars': 0,
                'confidence': 0.0,
            }
        if self._doc_type == 'pdf':
            if not self._doc:
                return {'is_text_based': False, 'page_types': [], 'text_page_count': 0, 'image_page_count': 0}
            return PDFTypeDetector.detect(self._doc)

        elif self._doc_type == 'word':
            is_text = bool(self._word_text.strip())
            return {
                'is_text_based': is_text,
                'page_types': ['text'] if is_text else ['image'],
                'text_page_count': 1 if is_text else 0,
                'image_page_count': 0 if is_text else 1,
                'total_text_chars': len(self._word_text),
                'confidence': 1.0 if is_text else 0.0,
            }
        elif self._doc_type == 'image':
            return {
                'is_text_based': False,
                'page_types': ['image'],
                'text_page_count': 0,
                'image_page_count': 1,
                'total_text_chars': 0,
                'confidence': 0.0,
            }
        return {'is_text_based': False, 'page_types': [], 'text_page_count': 0, 'image_page_count': 0}
    
    def extract_text_with_positions(self, page_num: int) -> list:
        if self._doc_type in ('adobe_image_pdf', 'adobe_live'):
            # Adobe 渲染模式 / 窗口捕获模式得到的是图片，无法直接给出坐标文本，返回空列表
            return []
        if self._doc_type == 'pdf':
            if not self._doc or page_num < 0 or page_num >= self._doc.page_count:
                return []
            try:
                page = self._doc[page_num]
                blocks = page.get_text('dict')['blocks']
                results = []
                for block in blocks:
                    if block['type'] == 0:
                        for line in block['lines']:
                            for span in line['spans']:
                                bbox = span['bbox']
                                results.append({
                                    'x0': bbox[0], 'y0': bbox[1],
                                    'x1': bbox[2], 'y1': bbox[3],
                                    'text': span['text']
                                })
                return results
            except Exception:
                return []
        elif self._doc_type == 'word':

            # Word 没有精确坐标，返回虚拟文本块
            results = []
            y = 0
            for text in self._word_paragraphs:
                if text.strip():
                    results.append({
                        'x0': 0, 'y0': y,
                        'x1': 800, 'y1': y + 20,
                        'text': text.strip()
                    })
                    y += 25
            return results
        return []
    
    def extract_text_in_rect(self, page_num: int, rect: List[float]) -> Optional[str]:
        """区域文本提取：PDF 按坐标；Word 按关键字搜索；图片 / Adobe 模式返回 None（走 OCR）"""
        if self._doc_type in ('adobe_image_pdf', 'adobe_live'):
            return None
        if self._doc_type == 'pdf':

            if not self._doc:
                return None
            try:
                page = self._doc[page_num]
                x0, y0, x1, y1 = rect
                blocks = page.get_text('dict', flags=fitz.TEXT_PRESERVE_WHITESPACE)['blocks']
                matched_texts = []
                for block in blocks:
                    if block['type'] != 0:
                        continue
                    for line in block['lines']:
                        for span in line['spans']:
                            bbox = span['bbox']
                            if (bbox[0] < x1 and bbox[2] > x0 and
                                bbox[1] < y1 and bbox[3] > y0):
                                matched_texts.append(span['text'])
                if matched_texts:
                    return ' '.join(matched_texts).strip()
            except Exception:
                pass
        elif self._doc_type == 'word':
            # Word 无法精确按坐标，返回全文（后续由字段逻辑做文本匹配）
            return self._word_text if self._word_text else None
        return None
    
    def get_word_text(self) -> str:
        """获取 Word 文档完整文本"""
        return self._word_text
    
    def get_word_paragraphs(self) -> List[str]:
        """获取 Word 段落列表"""
        return self._word_paragraphs
    
    def render_page(self, page_num: int, dpi: int = 300) -> Optional[Tuple[np.ndarray, float]]:
        if self._doc_type in ('adobe_image_pdf', 'adobe_live'):
            # Adobe Reader 已渲染成图片 / 窗口捕获模式，直接读取
            if page_num < 0 or page_num >= self._image_page_count:
                return None
            try:
                img = Image.open(self._adobe_images[page_num]).convert('RGB')
                # Adobe截图分辨率可能较低（取决于屏幕分辨率），
                # 按需放大图像以提升OCR精度
                w, h = img.size
                target_dpi = max(dpi, 300)  # 至少300 DPI
                scale = max(1.0, target_dpi / 150.0)  # 截图约150DPI
                if scale > 1.0:
                    new_w = int(w * scale)
                    new_h = int(h * scale)
                    img = img.resize((new_w, new_h), Image.LANCZOS)
                img_array = np.array(img)
                return (img_array, float(img.height))
            except Exception:
                return None
        if self._doc_type == 'pdf':
            if not self._doc or page_num < 0 or page_num >= self._doc.page_count:
                return None
            try:
                page = self._doc[page_num]
                zoom = dpi / 72.0
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                img_array = np.array(img)
                return (img_array, page.rect.height)
            except Exception:
                return None
        elif self._doc_type == 'image':
            if self._image_array is not None:
                return (self._image_array, float(self._image_array.shape[0]))
            return None
        elif self._doc_type == 'word':
            # 将 Word 文本渲染为文本图像，便于显示
            return self._render_word_as_image()
        return None

    
    def _render_word_as_image(self) -> Optional[Tuple[np.ndarray, float]]:
        """把 Word 文本渲染成一张可显示的图像"""
        try:
            width, line_height = 800, 24
            max_lines = max(len(self._word_paragraphs), 1)
            height = max_lines * line_height + 40
            img = Image.new('RGB', (width, height), color=(255, 255, 255))
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype('msyh.ttc', 16)
            except Exception:
                font = ImageFont.load_default()
            y = 10
            for para in self._word_paragraphs:
                if para.strip():
                    draw.text((10, y), para.strip(), fill=(0, 0, 0), font=font)
                    y += line_height
            img_array = np.array(img)
            return (img_array, float(height))
        except Exception:
            return None
    
    def get_page_rect(self, page_num: int) -> Optional[fitz.Rect]:
        if self._doc_type == 'pdf':
            if not self._doc or page_num < 0 or page_num >= self._doc.page_count:
                return None
            return self._doc[page_num].rect
        elif self._doc_type in ('image', 'word', 'adobe_image_pdf', 'adobe_live'):
            render_result = self.render_page(page_num)
            if render_result:
                img, height = render_result
                return fitz.Rect(0, 0, img.shape[1], height)
        return None

    
    def get_doc(self):
        return self._doc


# 保留旧类名兼容性
PDFRenderer = DocumentLoader


# =========================== 安全校验器 ===========================

# 全局共享 OCR 引擎（首次访问时初始化，所有 ReportChecker 实例复用，避免重复加载模型导致卡死）
_SHARED_OCR_ENGINE = None


def get_shared_ocr_engine() -> 'MultiOCREngine':
    """延迟初始化并复用全局 OCR 引擎，避免每个文件都重新加载模型"""
    global _SHARED_OCR_ENGINE
    if _SHARED_OCR_ENGINE is None:
        _SHARED_OCR_ENGINE = MultiOCREngine()
    return _SHARED_OCR_ENGINE


class ReportChecker:
    """报告校验核心类，整合文档识别 + 多引擎 OCR + 规则校验"""

    def __init__(self, ocr_engine=None):
        self._document_loader = DocumentLoader()
        # OCR 引擎延迟到首次真正使用时再初始化（避免打开文档时就卡死加载模型）
        self._ocr_engine = ocr_engine  # 可能为 None，首次访问时通过 get_shared_ocr_engine() 懒加载
        self._current_template = None
        self._extracted_data = {}
        self._errors = []
        self._pdf_type_info = None
        self._extraction_method = ""  # 记录使用的提取方法
        self._ocr_page_cache: Dict[int, str] = {}  # 整页 OCR 文本缓存（按页号）

    @property
    def ocr_engine(self):
        """惰性获取共享 OCR 引擎（首次访问才初始化）"""
        if self._ocr_engine is None:
            self._ocr_engine = get_shared_ocr_engine()
        return self._ocr_engine
    
    # ──────────── 文档操作 ────────────
    
    def open_document(self, file_path: str) -> bool:
        """打开文档（PDF / Word / 图片）"""
        result = self._document_loader.open_document(file_path)
        if result:
            self._pdf_type_info = self._document_loader.detect_pdf_type()
        return result
    
    def open_pdf(self, file_path: str) -> bool:
        """兼容旧接口：打开 PDF"""
        return self.open_document(file_path)
    
    def close_document(self):
        self._document_loader.close_document()
    
    def close_pdf(self):
        """兼容旧接口"""
        self.close_document()
    
    def get_document_type(self) -> str:
        """获取当前文档类型"""
        return self._document_loader.get_document_type()
    
    def get_pdf_type_info(self) -> Dict[str, Any]:
        """获取文档类型检测信息"""
        return self._pdf_type_info or {}
    
    def get_extraction_method(self) -> str:
        """获取当前使用的提取方法"""
        return self._extraction_method or "未执行"
    
    # ──────────── 模板 ────────────
    
    def load_template(self, template_name: str) -> bool:
        from config import get_template_path
        template_path = get_template_path(template_name)
        self._current_template = read_json_file(template_path)
        return self._current_template is not None
    
    # ──────────── 字段提取（核心分流域）────────────
    
    def extract_field(self, field_def: Dict[str, Any]) -> Optional[Any]:
        """
        根据文档类型智能选择提取方式：
          - Word 文档 → 文本搜索匹配（按描述关键字）
          - 文字型 PDF → PyMuPDF 直接提取文本（快速、准确）
          - 图片型 PDF / 图片 → OCR 级联链
          - number_array → 表格行多列数值数组（温升模板专用）
        """
        doc_type = self._document_loader.get_document_type()

        if doc_type == 'word':
            # Word 文档：按字段描述在文本中搜索
            self._extraction_method = "Word 文本搜索"
            return self._extract_field_word_text(field_def)

        page_num = field_def.get('page_num', 0)
        rect = field_def.get('rect', [0, 0, 100, 100])
        field_type = field_def.get('type', 'number')

        # number_array 类型：表格行多列数值（如温升表5列数据）
        if field_type == 'number_array':
            return self._extract_number_array(field_def)

        is_text_based = (self._pdf_type_info and
                        self._pdf_type_info.get('is_text_based', False))

        if is_text_based:
            # ── 方法1：文字型 PDF → 直接提取 ──
            self._extraction_method = "PyMuPDF 文本提取"
            return self._extract_field_text_direct(page_num, rect, field_type, field_def)
        else:
            # ── 方法2/3/4：图片型 PDF / 图片 → OCR 级联 ──
            return self._extract_field_ocr_chain(page_num, rect, field_type, field_def)

    def _extract_number_array(self, field_def: Dict[str, Any]) -> Optional[list]:
        """
        提取表格行中多个列的数值数组（温升模板专用）。
        
        策略：
          1. 文字型 PDF → PyMuPDF 提取该行文本，按列分割
          2. 图片型 PDF → OCR 整页文本，按行标签定位行，提取行内数值
          3. 最终都尝试从行文本中提取多个数值
        """
        field_name = field_def.get('field_name', '')
        description = field_def.get('description', '')
        page_num = field_def.get('page_num', 0)
        size = field_def.get('size', 5)

        is_text_based = (self._pdf_type_info and
                        self._pdf_type_info.get('is_text_based', False))

        # 获取页面文本
        page_text = ""
        if is_text_based:
            try:
                page = self._document_loader._doc[page_num]
                page_text = page.get_text() or ""
            except Exception:
                page_text = ""
        else:
            # 图片型 PDF：用缓存的整页 OCR 文本
            page_text = self._ocr_page_cache.get(page_num, "")

        if not page_text:
            return None

        # 在整页文本中按描述关键字定位行
        # 描述如 "冷态电阻 R1 (Ω)" → 在文本中找包含 "冷态电阻" 的行
        values = self._extract_array_from_text(page_text, description, size)

        if values is not None:
            self._extraction_method = "表格行数值数组提取"
            return values

        return None

    def _extract_array_from_text(self, text: str, description: str,
                                   size: int) -> Optional[list]:
        """
        从文本中根据描述关键字定位行，提取行内所有数值。
        
        例如描述 "冷态电阻 R1 (Ω)"，在文本中找包含 "冷态电阻" 的行，
        然后从该行提取所有数值返回数组。
        """
        if not text or not description:
            return None

        # 提取描述中的关键字（取前2-4个字）
        keywords = self._extract_keywords(description)
        if not keywords:
            return None

        lines = text.split('\n')
        for line in lines:
            # 检查行是否包含关键字
            matched = False
            for kw in keywords:
                if kw in line:
                    matched = True
                    break
            if not matched:
                continue

            # 从匹配行提取所有数值
            import re
            # 匹配整数、小数、负数
            numbers = re.findall(r'-?\d+\.?\d*', line)
            # 过滤掉可能不是数据的短数字（如行号、序号）
            parsed = []
            for s in numbers:
                try:
                    v = float(s)
                    # 温升数据通常在 -50 ~ 500 范围
                    if -100 < v < 1000:
                        parsed.append(v)
                except ValueError:
                    pass

            if len(parsed) >= 1:
                # 补齐或截取到指定 size
                while len(parsed) < size:
                    parsed.append(None)
                return parsed[:size]

        return None

    @staticmethod
    def _extract_keywords(description: str) -> list:
        """从描述文本中提取搜索关键字"""
        if not description:
            return []
        # 去掉单位括号部分
        import re
        clean = re.sub(r'\([^)]*\)', '', description)
        clean = clean.strip()
        # 取关键部分
        keywords = []
        # 尝试2字、3字、4字前缀
        for length in [4, 3, 2]:
            if len(clean) >= length:
                kw = clean[:length]
                if kw not in keywords:
                    keywords.append(kw)
        # 也尝试去掉常见前缀后的词
        for sep in [' ', '=', '（', '(', '：', ':']:
            if sep in clean:
                parts = clean.split(sep)
                for p in parts:
                    p = p.strip()
                    if len(p) >= 2:
                        keywords.append(p[:4])
                        break
                break
        return keywords
    
    def _extract_field_word_text(self, field_def: Dict[str, Any]) -> Optional[Any]:
        """Word 文档：根据字段描述在文本中搜索最近数字/文本"""
        text = self._document_loader.get_word_text()
        if not text:
            return None
        
        description = field_def.get('description', '')
        field_type = field_def.get('type', 'number')
        
        # 如果没有描述，则返回全文中的第一个数字/文本
        if not description:
            if field_type == 'number':
                return parse_number(text)
            else:
                return text.strip()[:200]
        
        # 1. 先尝试在同一行中匹配 "描述 + 值" 的模式
        paragraphs = self._document_loader.get_word_paragraphs()
        for para in paragraphs:
            if description in para:
                # 提取描述后面的数字或文本
                after = para.split(description, 1)[-1]
                if field_type == 'number':
                    value = parse_number(after)
                    if value is not None:
                        return value
                else:
                    # 取后面非空文本
                    after = after.strip().strip(':：').strip()
                    if after:
                        return after
        
        # 2. 描述不在同一段落，则全文查找第一个数字/文本
        if field_type == 'number':
            return parse_number(text)
        else:
            return text.strip()[:200]
    
    def _extract_field_text_direct(self, page_num: int, rect: List[float],
                                    field_type: str, field_def: Dict = None) -> Optional[float]:
        """文字型 PDF：PyMuPDF 直接提取矩形内文本"""
        text = self._document_loader.extract_text_in_rect(page_num, rect)

        if text:
            if field_type == 'number':
                return parse_number(text)
            else:
                return text

        # 区域直接提取失败：降级到『整页文本 + 字段描述关键字搜索』
        self._extraction_method = "PyMuPDF 区域提取失败 → 整页文本关键字匹配"
        desc = (field_def or {}).get('description', '')
        return self._extract_field_text_by_keyword(page_num, field_type, desc)

    def _extract_field_text_by_keyword(self, page_num: int, field_type: str,
                                        description: str = '') -> Optional[Any]:
        """文字型 PDF 兆底：在本页整页文本中按字段描述搜索数值/文本"""
        if not self._current_template or not description:
            return None
        # 整页文本
        try:
            page = self._document_loader._doc[page_num]
            full_text = page.get_text() or ""
        except Exception:
            full_text = ""
        if not full_text:
            return None
        # 使用当前字段的描述进行搜索
        return self._search_value_in_text(full_text, description, field_type)
    
    def _extract_field_ocr_chain(self, page_num: int, rect: List[float],
                                  field_type: str, field_def: Dict = None) -> Optional[float]:
        """图片型 PDF / 图片：优先用『整页 OCR 缓存 + 字段描述关键字』取值

        设计：
          - 整页只 OCR 一次（extract_all_fields 阶段已缓存到 _ocr_page_cache）
          - 字段提取时，在本页整页 OCR 文本中按描述定位数值，避免依赖
            精确矩形坐标（模板坐标与实际报告常不匹配导致提取失败/准确率低）
          - 若关键字匹配失败，再回退到矩形区域裁剪单独 OCR（兜底）
        """
        # 1) 优先：整页 OCR 缓存 + 关键字定位（使用当前字段自己的描述）
        page_text = self._ocr_page_cache.get(page_num, "")
        if page_text:
            desc = (field_def or {}).get('description', '')
            if desc:
                val = self._search_value_in_text(page_text, desc, field_type)
                if val is not None:
                    self._extraction_method = "OCR 整页缓存+关键字匹配"
                    return val

        # 2) 兜底：矩形区域单独 OCR
        render_result = self._document_loader.render_page(page_num)
        if not render_result:
            return None

        img_array, page_height = render_result

        x0, y0, x1, y1 = rect
        zoom = img_array.shape[0] / page_height

        left = int(x0 * zoom)
        bottom = int(y0 * zoom)
        right = int(x1 * zoom)
        top = int(y1 * zoom)

        pixmap_top = img_array.shape[0] - top
        pixmap_bottom = img_array.shape[0] - bottom

        left = max(0, left)
        pixmap_top = max(0, pixmap_top)
        right = min(img_array.shape[1], right)
        pixmap_bottom = min(img_array.shape[0], pixmap_bottom)

        if left >= right or pixmap_top >= pixmap_bottom:
            return None

        region_img = img_array[pixmap_top:pixmap_bottom, left:right]

        # 自动预处理：对比度增强 + 去噪，提高小区域识别率
        region_img = self._auto_preprocess_region(region_img)

        text = self.ocr_engine.recognize_region(region_img)
        self._extraction_method = f"OCR ({self.ocr_engine.get_current_engine_name()})"

        if field_type == 'number':
            return parse_number(text)
        else:
            return text

    @staticmethod
    def _auto_preprocess_region(image: np.ndarray) -> np.ndarray:
        """对小区域图像做自适应二值化 + 对比度增强 + 去噪，提高 OCR 识别率"""
        if image.size == 0:
            return image
        try:
            import cv2
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if len(image.shape) == 3 else image
            # 自适应二值化
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 15, 4)
            result = cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)
            return result
        except Exception:
            return image

    def _current_field_desc(self, page_num: int) -> str:
        """取同一页第一个含描述的字段描述（用于关键字定位）"""
        if not self._current_template:
            return ""
        for f in self._current_template.get('fields', []):
            if f.get('page_num', 0) == page_num:
                d = f.get('description', '')
                if d:
                    return d
        return ""

    def _search_value_in_text(self, text: str, description: str,
                                 field_type: str) -> Optional[Any]:
        """在本页整页 OCR/文本中提取值，支持表格结构

        表格结构识别：
          - 水平键值对：描述在左，值在右（如 "开始室温 t1  23.5"）
          - 垂直列头：描述在上，值在下（如 "冷态电阻R(Ω)" 下方是数值）
          - 数据网格：多行多列，按行标签+列头定位

        多策略查找：
          1. 精确匹配完整描述
          2. 描述前缀匹配（取前 4~6 字）
          3. 逐词拆分匹配（去掉单位/括号等修饰词后查找核心词）
          4. 跨行匹配（描述在一行，数值在下一行同一列位置）
          5. 表格网格匹配（识别表头+数据行结构）
        """
        idx = -1
        desc_len = 0

        # 策略 1：精确匹配
        idx = text.find(description)
        if idx >= 0:
            desc_len = len(description)

        # 策略 2：前缀匹配
        if idx < 0 and len(description) >= 4:
            for prefix_len in range(min(6, len(description)), 3, -1):
                idx = text.find(description[:prefix_len])
                if idx >= 0:
                    desc_len = prefix_len
                    break

        # 策略 3：核心词匹配（去掉单位、括号修饰）
        if idx < 0:
            core = re.sub(r'[\(\)（）\[\]【】].*$', '', description).strip()
            core = re.sub(r'[\d\s°℃KkVvAaWw]+$', '', core).strip()
            if len(core) >= 2:
                idx = text.find(core)
                if idx >= 0:
                    desc_len = len(core)

        if idx < 0:
            return None

        # 取描述后 200 字符作为候选区（含换行，扩大范围以覆盖表格结构）
        after = text[idx + desc_len: idx + desc_len + 200]

        if field_type == 'number':
            # 策略 4：直接取描述后的第一个数字（水平键值对）
            val = parse_number(after)
            if val is not None:
                return val

            # 策略 5：表格结构——描述是列头，值在下方数据行中
            # 将 after 按行拆分，尝试在后续行中找到数字
            lines = after.split('\n')
            for line in lines[1:6]:  # 检查后续最多 5 行
                line = line.strip()
                if not line:
                    continue
                # 尝试从行中提取第一个数字
                val = parse_number(line)
                if val is not None:
                    return val

            return None

        # 文本类型：取同行或下一行
        after_clean = after.strip().split('\n')[0].strip(':：').strip()
        if after_clean:
            return after_clean
        # 尝试下一行
        lines = after.strip().split('\n')
        if len(lines) > 1:
            next_line = lines[1].strip()
            if next_line:
                return next_line
        return None

    def extract_all_fields(self) -> Dict[str, Any]:
        if not self._current_template:
            return {}

        self._extracted_data = {}
        fields = self._current_template.get('fields', [])

        # 图片型 PDF：先对涉及的每一页做『整页 OCR 一次』并缓存，
        # 后续字段提取复用缓存（按描述关键字定位），避免逐字段重复 OCR 导致极慢。
        self._ocr_page_cache: Dict[int, str] = {}
        if not self.is_text_based_pdf():
            page_set = sorted({f.get('page_num', 0) for f in fields})
            for p in page_set:
                try:
                    render_result = self._document_loader.render_page(p)
                    if render_result:
                        img, _ = render_result
                        txt = self.ocr_engine.recognize_region(img) or ""
                        self._ocr_page_cache[p] = txt
                except Exception:
                    continue

        for field in fields:
            field_name = field.get('field_name', '')
            if field_name:
                self._extracted_data[field_name] = self.extract_field(field)
        
        return self._extracted_data
    
    # ──────────── 规则校验 ────────────
    
    def _current_measure_method(self) -> Optional[str]:
        """根据模板 method_field 判定当前报告的测量方法"""
        if not self._current_template:
            return None
        method_field = self._current_template.get('method_field', '')
        if not method_field:
            return None
        raw = self._extracted_data.get(method_field)
        if not raw or not isinstance(raw, str):
            return None
        if '电阻' in raw:
            return 'resistance'
        if '热电偶' in raw or '热偶' in raw:
            return 'thermocouple'
        return None

    def check_rules(self) -> List[Dict[str, Any]]:
        self._errors = []

        if not self._current_template or not self._extracted_data:
            return self._errors

        rules = self._current_template.get('rules', [])
        current_method = self._current_measure_method()

        for rule in rules:
            # 跳过模板中的注释占位对象
            if rule.get('_comment') or not rule.get('type'):
                continue

            rule_type = rule.get('type', '')
            field_name = rule.get('field_name', '')
            expected = rule.get('expected', None)
            limit = rule.get('limit', None)
            operator = rule.get('operator', '<=')
            unit = rule.get('unit', '')
            formula = rule.get('formula', '')
            rule_method = rule.get('method', '')

            # 方法过滤：规则指定了方法，且当前报告方法已知且与规则不符 → 跳过
            if rule_method and current_method and rule_method != current_method:
                continue

            actual_value = self._extracted_data.get(field_name)
            field_desc = self._get_field_desc(field_name)

            if actual_value is None:
                # 带方法约束的规则：当前方法不明（未识别出电阻法/热电偶法）时，
                # 不强行报缺失，避免报告只用了一种方法却误报另一种方法的字段缺失
                if rule_method and not current_method:
                    continue
                self._errors.append({
                    'level': 'error',
                    'field': field_name,
                    'message': f"{field_desc}：未识别到数据",
                    'page_num': self._get_field_page_num(field_name),
                    'rect': self._get_field_rect(field_name),
                })
                continue

            if rule_type == 'calculation':
                if formula:
                    calc_value = self._calculate_formula(formula)
                    if calc_value is not None:
                        tolerance = rule.get('tolerance', TOLERANCE.get('calculation', 2.0))
                        if not check_tolerance(calc_value, actual_value, tolerance):
                            self._errors.append({
                                'level': 'warning',
                                'field': field_name,
                                'message': f"{field_desc}：记录值 {actual_value}{unit}，按公式应为 {calc_value:.1f}{unit}，偏差 {abs(actual_value - calc_value):.1f}{unit}",
                                'page_num': self._get_field_page_num(field_name),
                                'rect': self._get_field_rect(field_name),
                                'calculated_value': calc_value,
                                'formula': formula,
                            })
                        else:
                            self._errors.append({
                                'level': 'info',
                                'field': field_name,
                                'message': f"{field_desc}：记录值 {actual_value}{unit}，计算值 {calc_value:.1f}{unit}，一致",
                                'page_num': self._get_field_page_num(field_name),
                                'rect': self._get_field_rect(field_name),
                                'calculated_value': calc_value,
                                'formula': formula,
                            })

            elif rule_type == 'limit':
                # 支持数组型字段的限值检查
                values_to_check = []
                if isinstance(actual_value, list):
                    for i, v in enumerate(actual_value):
                        if isinstance(v, (int, float)):
                            values_to_check.append((i, v))
                elif isinstance(actual_value, (int, float)):
                    values_to_check.append((None, actual_value))

                if limit is not None and values_to_check:
                    for col_idx, val in values_to_check:
                        col_label = f" 第{col_idx+1}列" if col_idx is not None else ""
                        if not check_limit(val, limit, operator):
                            self._errors.append({
                                'level': 'error',
                                'field': f"{field_name}[{col_idx}]" if col_idx is not None else field_name,
                                'message': f"{field_desc}{col_label}：{val}{unit} {operator} {limit}{unit}，超出标准限值",
                                'page_num': self._get_field_page_num(field_name),
                                'limit': limit,
                                'operator': operator,
                            })
                        else:
                            self._errors.append({
                                'level': 'info',
                                'field': f"{field_name}[{col_idx}]" if col_idx is not None else field_name,
                                'message': f"{field_desc}{col_label}：{val}{unit} {operator} {limit}{unit}，符合标准",
                                'page_num': self._get_field_page_num(field_name),
                                'limit': limit,
                                'operator': operator,
                            })

            elif rule_type == 'tolerance':
                # 支持数组型字段：比较两个数组或数组与固定值
                if expected is not None:
                    # 两个字段名比较的情况
                    field_b = rule.get('field_name_b', '')
                    if field_b:
                        value_b = self._extracted_data.get(field_b)
                        self._check_tolerance_array(
                            rule, field_name, field_desc, unit,
                            actual_value, value_b)
                    elif isinstance(actual_value, list):
                        # 数组 vs 固定值
                        for i, v in enumerate(actual_value):
                            if isinstance(v, (int, float)):
                                tolerance = rule.get('tolerance', TOLERANCE.get('numeric', 5.0))
                                if not check_tolerance(v, expected, tolerance):
                                    self._errors.append({
                                        'level': 'warning',
                                        'field': f"{field_name}[{i}]",
                                        'message': f"{field_desc} 第{i+1}列：{v}{unit}，标准值 {expected}{unit}，偏差 {abs(v - expected):.1f}{unit}",
                                        'page_num': self._get_field_page_num(field_name),
                                        'expected': expected,
                                    })
                    elif isinstance(actual_value, (int, float)):
                        tolerance = rule.get('tolerance', TOLERANCE.get('numeric', 5.0))
                        if not check_tolerance(actual_value, expected, tolerance):
                            deviation = abs(actual_value - expected)
                            self._errors.append({
                                'level': 'warning',
                                'field': field_name,
                                'message': f"{field_desc}：{actual_value}{unit}，标准值 {expected}{unit}，偏差 {deviation:.1f}{unit}",
                                'page_num': self._get_field_page_num(field_name),
                                'expected': expected,
                            })
                        else:
                            self._errors.append({
                                'level': 'info',
                                'field': field_name,
                                'message': f"{field_desc}：{actual_value}{unit}，标准值 {expected}{unit}，符合",
                                'page_num': self._get_field_page_num(field_name),
                                'expected': expected,
                            })

            elif rule_type == 'formula_verify':
                # 温升模板专用：验证公式计算值与 OCR 提取值的一致性
                # 支持数组型字段逐列验证
                self._check_formula_verify(rule, field_name, actual_value, field_desc, unit, formula)

        return self._errors

    def _check_formula_verify(self, rule: Dict, field_name: str,
                               actual_value: Any, field_desc: str,
                               unit: str, formula: str):
        """
        公式验证规则处理。
        
        对于数组型字段（如 rise_resistance = [68.6, 57.1, ...]），
        逐列验证每个值是否与公式计算结果一致。
        对于单个数值字段，直接验证。
        """
        if not formula:
            formula = rule.get('formula', '')
        if not formula:
            return

        tolerance_pct = rule.get('tolerance_pct', 1.0)
        message = rule.get('message', f"{field_desc}公式验证偏差过大")

        if isinstance(actual_value, list):
            # 数组型字段：逐列验证
            calc_values = self._calculate_formula_array(formula)
            if calc_values is None:
                # 尝试逐列计算
                calc_values = self._calculate_formula_per_element(formula, len(actual_value))

            if calc_values is not None:
                for i, (actual, calc) in enumerate(zip(actual_value, calc_values)):
                    if actual is None or calc is None:
                        continue
                    if isinstance(actual, (int, float)) and isinstance(calc, (int, float)):
                        pct_diff = abs(actual - calc) / max(abs(calc), 0.1) * 100
                        if pct_diff > tolerance_pct:
                            self._errors.append({
                                'level': 'warning',
                                'field': f"{field_name}[{i}]",
                                'message': f"{field_desc} 第{i+1}列：记录值 {actual:.1f}{unit}，公式计算 {calc:.1f}{unit}，偏差 {pct_diff:.1f}%",
                                'page_num': self._get_field_page_num(field_name),
                                'calculated_value': calc,
                                'formula': formula,
                                'column': i,
                            })
                        else:
                            self._errors.append({
                                'level': 'info',
                                'field': f"{field_name}[{i}]",
                                'message': f"{field_desc} 第{i+1}列：记录值 {actual:.1f}{unit}，公式计算 {calc:.1f}{unit}，一致",
                                'page_num': self._get_field_page_num(field_name),
                                'calculated_value': calc,
                                'formula': formula,
                                'column': i,
                            })
        elif isinstance(actual_value, (int, float)):
            # 单值字段验证
            calc_value = self._calculate_formula(formula)
            if calc_value is not None and isinstance(calc_value, (int, float)):
                pct_diff = abs(actual_value - calc_value) / max(abs(calc_value), 0.1) * 100
                if pct_diff > tolerance_pct:
                    self._errors.append({
                        'level': 'warning',
                        'field': field_name,
                        'message': f"{field_desc}：记录值 {actual_value:.1f}{unit}，公式计算 {calc_value:.1f}{unit}，偏差 {pct_diff:.1f}%",
                        'page_num': self._get_field_page_num(field_name),
                        'calculated_value': calc_value,
                        'formula': formula,
                    })
                else:
                    self._errors.append({
                        'level': 'info',
                        'field': field_name,
                        'message': f"{field_desc}：记录值 {actual_value:.1f}{unit}，公式计算 {calc_value:.1f}{unit}，一致",
                        'page_num': self._get_field_page_num(field_name),
                        'calculated_value': calc_value,
                        'formula': formula,
                    })

    def _check_tolerance_array(self, rule: Dict, field_name: str,
                                field_desc: str, unit: str,
                                value_a: Any, value_b: Any):
        """
        比较两个字段的值是否在容差范围内。
        支持数组 vs 数组、数组 vs 单值、单值 vs 单值。
        """
        max_diff = rule.get('max_diff', rule.get('tolerance', TOLERANCE.get('numeric', 5.0)))
        message = rule.get('message', f"{field_desc} 偏差过大")

        # 统一为数组形式
        if isinstance(value_a, list) and isinstance(value_b, list):
            # 数组 vs 数组：逐列比较
            for i in range(max(len(value_a), len(value_b))):
                va = value_a[i] if i < len(value_a) else None
                vb = value_b[i] if i < len(value_b) else None
                if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                    diff = abs(va - vb)
                    if diff > max_diff:
                        self._errors.append({
                            'level': 'warning',
                            'field': f"{field_name}[{i}]",
                            'message': f"{field_desc} 第{i+1}列：{field_desc.split(',')[0]}={va}{unit}，对比值={vb}{unit}，差值 {diff:.1f}{unit} > {max_diff}{unit}",
                            'page_num': self._get_field_page_num(field_name),
                        })
                    else:
                        self._errors.append({
                            'level': 'info',
                            'field': f"{field_name}[{i}]",
                            'message': f"{field_desc} 第{i+1}列：差值 {diff:.1f}{unit} ≤ {max_diff}{unit}，符合",
                            'page_num': self._get_field_page_num(field_name),
                        })
        elif isinstance(value_a, list) and isinstance(value_b, (int, float)):
            # 数组 vs 单值
            for i, va in enumerate(value_a):
                if isinstance(va, (int, float)):
                    diff = abs(va - value_b)
                    if diff > max_diff:
                        self._errors.append({
                            'level': 'warning',
                            'field': f"{field_name}[{i}]",
                            'message': f"{field_desc} 第{i+1}列：{va}{unit}，对比值 {value_b}{unit}，差值 {diff:.1f}{unit} > {max_diff}{unit}",
                            'page_num': self._get_field_page_num(field_name),
                        })
        elif isinstance(value_a, (int, float)) and isinstance(value_b, (int, float)):
            # 单值 vs 单值
            diff = abs(value_a - value_b)
            if diff > max_diff:
                self._errors.append({
                    'level': 'warning',
                    'field': field_name,
                    'message': f"{field_desc}：{value_a}{unit}，对比值 {value_b}{unit}，差值 {diff:.1f}{unit} > {max_diff}{unit}",
                    'page_num': self._get_field_page_num(field_name),
                })
            else:
                self._errors.append({
                    'level': 'info',
                    'field': field_name,
                    'message': f"{field_desc}：差值 {diff:.1f}{unit} ≤ {max_diff}{unit}，符合",
                    'page_num': self._get_field_page_num(field_name),
                })

    def _calculate_formula_array(self, formula: str) -> Optional[list]:
        """
        当公式中所有变量都是数组时，尝试逐元素计算。
        如果变量不是数组则回退到 _calculate_formula_per_element。
        """
        import re
        var_names = re.findall(r'[a-zA-Z_]\w*', formula)
        var_names = [v for v in var_names if v in self._extracted_data]

        if not var_names:
            return None

        # 检查是否所有变量都是数组
        all_arrays = True
        size = None
        for v in var_names:
            data = self._extracted_data.get(v)
            if isinstance(data, list):
                if size is None:
                    size = len(data)
            else:
                all_arrays = False

        if all_arrays and size:
            return self._calculate_formula_per_element(formula, size)

        return None

    def _calculate_formula_per_element(self, formula: str, size: int) -> Optional[list]:
        """
        对数组型公式逐元素计算。
        例如 rise_resistance = r_hot/r_cold*(235+t1)-(235+t2)
        当 r_hot、r_cold、t1、t2 都是数组时，逐列代入计算。
        """
        # 查找公式中所有变量名
        import re
        var_names = re.findall(r'[a-zA-Z_]\w*', formula)
        var_names = [v for v in var_names if v in self._extracted_data]

        # 检查所有变量是否都是数组且长度一致
        arrays = {}
        all_arrays = True
        for v in var_names:
            data = self._extracted_data.get(v)
            if isinstance(data, list):
                arrays[v] = data
            elif isinstance(data, (int, float)):
                # 单值变量也支持（如 t2 可能是单值）
                arrays[v] = [data] * size
                all_arrays = False
            else:
                return None

        results = []
        for i in range(size):
            local_vars = {}
            for v, arr in arrays.items():
                if i < len(arr) and arr[i] is not None:
                    local_vars[v] = arr[i]
                else:
                    # 缺数据，跳过
                    results.append(None)
                    continue
            try:
                result = eval(formula, {}, local_vars)
                if isinstance(result, (int, float)):
                    results.append(result)
                else:
                    results.append(None)
            except Exception:
                results.append(None)

        return results

    def _get_field_desc(self, field_name: str) -> str:
        """查找字段的中文描述，找不到则回退英文名"""
        if not self._current_template:
            return field_name
        for f in self._current_template.get('fields', []):
            if f.get('field_name') == field_name:
                return f.get('description', field_name)
        return field_name
    
    def _calculate_formula(self, formula: str) -> Optional[float]:
        try:
            local_vars = {}
            for key, value in self._extracted_data.items():
                if isinstance(value, (int, float)):
                    local_vars[key] = value
            result = eval(formula, {}, local_vars)
            if isinstance(result, (int, float)):
                return result
        except Exception:
            pass
        return None
    
    def _get_field_page_num(self, field_name: str) -> int:
        if not self._current_template:
            return 0
        for field in self._current_template.get('fields', []):
            if field.get('field_name') == field_name:
                return field.get('page_num', 0)
        return 0
    
    def _get_field_rect(self, field_name: str) -> List[float]:
        if not self._current_template:
            return [0, 0, 0, 0]
        for field in self._current_template.get('fields', []):
            if field.get('field_name') == field_name:
                return field.get('rect', [0, 0, 0, 0])
        return [0, 0, 0, 0]
    
    # ──────────── 批量检测 ────────────
    
    def auto_detect_templates(self) -> List[str]:
        """自动检测适用的模板（支持 PDF、Word、图片）"""
        from config import list_available_templates, get_template_path
        
        if not self._document_loader.get_doc():
            return []
        
        all_templates = list_available_templates()
        matched = []

        # 获取首页文本（支持图片型扫描件：get_text 为空时自动 OCR 兜底）
        doc_type = self._document_loader.get_document_type()
        # 用于匹配的合并文本（首页 + 必要时前几页，提高图片型/多页报告召回率）
        page0_text = ""
        try:
            if doc_type == 'pdf':
                page0_text = self._document_loader.get_doc()[0].get_text() or ""
            elif doc_type == 'word':
                page0_text = self._document_loader.get_word_text() or ""

            # 文本太少（<50字符）说明是图片型扫描件，需要 OCR 兜底
            if len(page0_text.strip()) < 50:
                # OCR 前 2 页并合并，避免数据在次页导致匹配失败
                ocr_parts = []
                max_ocr_pages = min(2, self._document_loader.get_page_count())
                for p in range(max_ocr_pages):
                    render_result = self._document_loader.render_page(p)
                    if not render_result:
                        continue
                    img, _ = render_result
                    t = (self.ocr_engine.recognize_region(img) or "").strip()
                    if t:
                        ocr_parts.append(t)
                ocr_text = "\n".join(ocr_parts)
                if len(ocr_text) >= 20:   # OCR 结果有效则使用
                    page0_text = ocr_text

            if doc_type == 'image' and not page0_text:
                render_result = self._document_loader.render_page(0)
                if render_result:
                    img, _ = render_result
                    page0_text = self.ocr_engine.recognize_region(img) or ""
        except Exception:
            pass   # page0_text 保持为空字符串

        for tmpl_name in all_templates:
            try:
                template_path = get_template_path(tmpl_name)
                if not os.path.exists(template_path):
                    continue

                tmpl = read_json_file(template_path)
                if not tmpl:
                    continue

                fields = tmpl.get('fields', [])
                page0_fields = [f for f in fields if f.get('page_num', 0) == 0]

                # 1. 字段描述匹配：将描述拆成 2 字以上片段，任一片段出现在文本中即计一次命中
                #    （报告原文常用简称如「定子」「温升」，整句描述反而不易直接命中）
                desc_hit = 0
                for f in page0_fields:
                    desc = f.get('description', '') or f.get('field_name', '')
                    if not desc or len(desc) < 2:
                        continue
                    # 取描述中的子串（长度>=2）做包含匹配
                    hit = False
                    for L in (4, 3, 2):
                        for i in range(0, len(desc) - L + 1):
                            frag = desc[i:i+L]
                            if frag in page0_text:
                                hit = True
                                break
                        if hit:
                            break
                    if hit:
                        desc_hit += 1

                # 2. 模板特征关键词匹配（模板可声明 match_keywords，用于区分易混淆报告）
                #    命中任一关键词即认为该模板可能适用
                keywords = tmpl.get('meta', {}).get('match_keywords', [])
                kw_hit = 0
                for kw in keywords:
                    if kw and kw in page0_text:
                        kw_hit += 1

                # 判定规则：
                #  - 有特征关键词的模板：关键词命中即匹配（强信号，避免被无关模板干扰）
                #  - 无特征关键词的模板：首页字段描述只需命中 1 个即视为候选
                #  - 完全没有首页字段的模板：仅靠关键词匹配，无关键词则默认不匹配
                if keywords:
                    matched_by_kw = kw_hit > 0
                else:
                    matched_by_kw = False

                if matched_by_kw or (page0_fields and desc_hit >= 1):
                    matched.append(tmpl_name)
            except Exception:
                continue

        return matched
    
    def batch_check(self, template_names: List[str], progress_callback=None) -> Dict[str, Any]:
        results = {}
        total = len(template_names)
        passed = 0
        failed = 0
        
        for idx, tmpl_name in enumerate(template_names):
            if progress_callback:
                progress_callback(idx + 1, total, tmpl_name)
            
            try:
                self.load_template(tmpl_name)
                self.extract_all_fields()
                errors = self.check_rules()
                
                error_count = sum(1 for e in errors if e.get('level') in ('error', 'warning'))
                
                results[tmpl_name] = {
                    'errors': errors,
                    'extracted_data': self._extracted_data.copy(),
                    'error_count': error_count,
                    'extraction_method': self._extraction_method,
                }
                
                if error_count == 0:
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                results[tmpl_name] = {
                    'errors': [{'level': 'error', 'field': '', 'message': f'校验异常: {str(e)}', 'page_num': 0, 'rect': [0]*4}],
                    'extracted_data': {},
                    'error_count': 1,
                    'extraction_method': '异常',
                }
                failed += 1
        
        return {
            'total': total,
            'passed': passed,
            'failed': failed,
            'results': results,
            'pdf_type': 'text' if self._pdf_type_info and self._pdf_type_info.get('is_text_based') else 'image',
        }
    
    def save_result(self, pdf_name: str) -> bool:
        result = {
            'pdf_name': pdf_name,
            'template': self._current_template.get('meta', {}) if self._current_template else {},
            'extracted_data': self._extracted_data,
            'errors': self._errors,
            'extraction_method': self._extraction_method,
        }
        result_path = os.path.join(RESULT_DIR, f'{pdf_name}_result.json')
        return write_json_file(result_path, result)
    
    # ──────────── 查询接口 ────────────
    
    def get_errors(self) -> List[Dict[str, Any]]:
        return self._errors
    
    def get_extracted_data(self) -> Dict[str, Any]:
        return self._extracted_data
    
    def is_ocr_available(self) -> bool:
        """检查是否有可用的 OCR 引擎（轻量预检，不加载/下载模型）"""
        # 注意：不要在这里触发 _ensure_initialized()，否则打开文字型 PDF 时
        # 也会强制加载（甚至联网下载）PaddleOCR 模型，导致打开/校验卡顿。
        # 仅做轻量依赖预检：是否已初始化且可用，或任一引擎的安装基础存在。
        engine = self.ocr_engine
        if engine._initialized:
            return engine.is_available()
        return engine.can_be_available()
    
    def get_ocr_engine_info(self) -> str:
        if hasattr(self.ocr_engine, 'get_engine_info'):
            return self.ocr_engine.get_engine_info()
        return f"引擎: {'可用' if self.is_ocr_available() else '不可用'}"
    
    def get_current_engine_name(self) -> str:
        if hasattr(self.ocr_engine, 'get_current_engine_name'):
            return self.ocr_engine.get_current_engine_name()
        return "未知"

    def set_ocr_engine(self, engine_name: str) -> bool:
        """切换 OCR 引擎（自动/手动）"""
        if hasattr(self.ocr_engine, 'set_forced_engine'):
            return self.ocr_engine.set_forced_engine(engine_name)
        return False
    
    def get_page_count(self) -> int:
        return self._document_loader.get_page_count()
    
    def render_page(self, page_num: int, dpi: int = 300) -> Optional[Tuple[np.ndarray, float]]:
        return self._document_loader.render_page(page_num, dpi)
    
    def is_text_based_pdf(self) -> bool:
        return self._document_loader.is_text_based_pdf()
    
    def render_page_with_highlight(self, page_num: int, dpi: int = 300,
                                    draw_boxes: bool = False,
                                    on_engine_try: Optional[callable] = None,
                                    on_engine_result: Optional[callable] = None) -> Optional[np.ndarray]:
        """
        渲染页面并叠加识别结果。

        Args:
            page_num: 页码
            dpi: 渲染 DPI
            draw_boxes: True=画出所有 OCR 识别框（含文字标注）；
                        False=仅高亮数字区域
            on_engine_try/on_engine_result: 级联识别时的回调，用于 GUI 高亮当前引擎标签

        Returns:
            (图像数组, 使用的引擎名) 或 (None, "")
        """
        render_result = self._document_loader.render_page(page_num, dpi)
        if not render_result:
            return None, ""

        img_array, page_height = render_result
        used_engine = ""

        if self._document_loader.is_text_based_pdf():
            text_blocks = self._document_loader.extract_text_with_positions(page_num)
            number_regions = []
            number_pattern = re.compile(r'\d')

            for block in text_blocks:
                if number_pattern.search(block['text']):
                    number_regions.append({
                        'x0': block['x0'], 'y0': block['y0'],
                        'x1': block['x1'], 'y1': block['y1'],
                        'text': block['text']
                    })

            # draw_boxes=True 时，画所有文本块的框（不仅是数字）
            if draw_boxes and text_blocks:
                img_h = img_array.shape[0]
                scale = img_h / page_height if page_height else 1.0
                ocr_items = []
                for b in text_blocks:
                    txt = b.get('text', '').strip()
                    if not txt:
                        continue
                    px0 = b['x0'] * scale
                    py0 = img_h - b['y1'] * scale  # PDF y 从底部起
                    px1 = b['x1'] * scale
                    py1 = img_h - b['y0'] * scale
                    box = [[px0, py0], [px1, py0], [px1, py1], [px0, py1]]
                    ocr_items.append([box, (txt, 1.0)])
                if ocr_items:
                    return draw_ocr_boxes(img_array, ocr_items), "文本层"

            if number_regions:
                return highlight_number_regions(img_array, number_regions, page_height), "文本层"
            return img_array, "文本层"
        else:
            # 图片型：走级联 OCR 引擎（带回调）
            if not self.is_ocr_available():
                return img_array, ""

            try:
                # 关键优化：一次 OCR 调用同时获取坐标和文本，避免 recognize_region
                # + _get_raw_ocr_result 两次 OCR 导致翻倍耗时
                raw, used_engine = self._get_raw_ocr_result_with_callbacks(
                    img_array, on_engine_try, on_engine_result,
                )
                if raw:
                    if draw_boxes:
                        return draw_ocr_boxes(img_array, raw), used_engine
                    regions = find_number_regions(raw)
                    if regions:
                        return highlight_number_regions(
                            img_array, regions, coords_are_pixels=True
                        ), used_engine
            except Exception:
                pass

        return img_array, used_engine

    def _get_raw_ocr_result_with_callbacks(self, image: np.ndarray,
                                            on_engine_try=None, on_engine_result=None):
        """一次 OCR 调用同时获取坐标+文本，并支持级联回调。
        返回 (raw_result, used_engine_name)，避免两次 OCR 翻倍耗时。"""
        try:
            # 先通过级联引擎完成一次识别（带回调，确保当前引擎已确定）
            self.ocr_engine._ensure_initialized()
            engine = getattr(self.ocr_engine, '_current_engine', None)
            used_name = ""
            if engine is not None and engine.is_available():
                name = engine.get_engine_name()
                if on_engine_try:
                    try:
                        on_engine_try(name, True)
                    except Exception:
                        pass
                ocr_obj = getattr(engine, '_ocr', None)
                raw = None
                if ocr_obj is not None and callable(ocr_obj):
                    res = ocr_obj(image)
                    if res and len(res) > 0:
                        raw = res[0] if isinstance(res[0], list) else res
                elif hasattr(engine, '_paddle') and engine._paddle is not None:
                    pad = engine._paddle
                    pad_obj = getattr(pad, '_ocr', None)
                    if pad_obj is not None:
                        res = pad_obj.ocr(image)
                        if res and len(res) > 0:
                            raw = res[0] if isinstance(res[0], list) else res
                ok = raw is not None and len(raw) > 0
                if on_engine_result:
                    try:
                        on_engine_result(name, ok)
                    except Exception:
                        pass
                if ok:
                    return raw, name
            # 当前引擎失败 → 级联其他引擎（同时收集原始结果）
            tried_ids = {id(engine)} if engine else set()
            for eng in self.ocr_engine._engines:
                if id(eng) in tried_ids or not eng.is_available():
                    continue
                name = eng.get_engine_name()
                if on_engine_try:
                    try:
                        on_engine_try(name, True)
                    except Exception:
                        pass
                ocr_obj = getattr(eng, '_ocr', None)
                raw = None
                if ocr_obj is not None and callable(ocr_obj):
                    res = ocr_obj(image)
                    if res and len(res) > 0:
                        raw = res[0] if isinstance(res[0], list) else res
                elif hasattr(eng, '_paddle') and eng._paddle is not None:
                    pad = eng._paddle
                    pad_obj = getattr(pad, '_ocr', None)
                    if pad_obj is not None:
                        res = pad_obj.ocr(image)
                        if res and len(res) > 0:
                            raw = res[0] if isinstance(res[0], list) else res
                ok = raw is not None and len(raw) > 0
                if on_engine_result:
                    try:
                        on_engine_result(name, ok)
                    except Exception:
                        pass
                if ok:
                    return raw, name
            return None, used_name or (engine.get_engine_name() if engine else "")
        except Exception:
            pass
        return None, ""

    def _get_raw_ocr_result(self, image: np.ndarray):
        """获取带坐标的 OCR 原始结果（优先当前级联引擎的底层实例）"""
        raw, _ = self._get_raw_ocr_result_with_callbacks(image)
        return raw

    def get_ocr_engine_list(self) -> List[Dict[str, Any]]:
        """返回 OCR 引擎列表（名称 + 可用性），供 GUI 渲染标签"""
        if hasattr(self.ocr_engine, 'get_engine_list'):
            return self.ocr_engine.get_engine_list()
        return []

    def get_current_ocr_engine_name(self) -> str:
        return self.ocr_engine.get_current_engine_name()

    def cross_verify_ocr(self, page_num: int,
                         on_progress: Optional[callable] = None
                         ) -> Dict[str, Any]:
        """多引擎交叉比对 OCR 识别

        Args:
            page_num: 页码
            on_progress: 进度回调 func(engine_name, current, total)

        Returns:
            {results, best_text, agreement, used_engines}
        """
        render_result = self.render_page(page_num)
        if not render_result:
            return {'results': {}, 'best_text': '', 'agreement': 0.0, 'used_engines': []}
        img, _ = render_result
        if hasattr(self.ocr_engine, 'recognize_region_cross_verify'):
            return self.ocr_engine.recognize_region_cross_verify(img, on_progress)
        # 兜底：单引擎
        text = self.ocr_engine.recognize_region(img)
        return {'results': {'single': text or ''}, 'best_text': text or '',
                'agreement': 1.0, 'used_engines': ['single']}

    # ──────────── OCR 缓存与比对 ────────────

    def cache_ocr_tables(self, template_name: str) -> Optional[Dict[str, Any]]:
        """
        按模板 tables 定义，对涉及的每页做 OCR，将识别结果按表格结构组织为 JSON。
        缓存到 result/{pdf_name}_ocr_cache.json
        """
        if not self.load_template(template_name):
            return None
        tmpl = self._current_template
        if not tmpl:
            return None

        tables_def = tmpl.get('tables', [])
        if not tables_def:
            return None

        # 收集需要 OCR 的页码
        page_set = sorted({tdef.get('page_num', 0) for tdef in tables_def})

        # 对每页做 OCR（复用已有缓存）
        for p in page_set:
            if p not in self._ocr_page_cache:
                try:
                    if self.is_text_based_pdf():
                        # 文字型 PDF 直接提取文本
                        try:
                            doc = self._document_loader._doc
                            if doc and 0 <= p < doc.page_count:
                                text = doc[p].get_text("text")
                                if text and text.strip():
                                    self._ocr_page_cache[p] = text.strip()
                                    continue
                        except Exception:
                            pass
                    # 图片型：渲染 + OCR
                    render_result = self._document_loader.render_page(p)
                    if render_result:
                        img, _ = render_result
                        txt = self.ocr_engine.recognize_region(img) or ""
                        self._ocr_page_cache[p] = txt
                except Exception:
                    self._ocr_page_cache[p] = ""

        # 按表格结构组织结果
        ocr_result = {
            'template': template_name,
            'tables': {}
        }

        for tdef in tables_def:
            tname = tdef.get('table_name', '')
            ttype = tdef.get('type', 'key_value')
            page_num = tdef.get('page_num', 0)
            page_text = self._ocr_page_cache.get(page_num, '')

            if ttype == 'key_value':
                ocr_result['tables'][tname] = self._extract_kv_from_text(
                    tdef, page_text)
            else:
                ocr_result['tables'][tname] = self._extract_grid_from_text(
                    tdef, page_text)

        # 缓存到文件
        pdf_name = os.path.splitext(
            os.path.basename(self._document_loader._file_path or 'unknown'))[0]
        cache_path = os.path.join(RESULT_DIR, f'{pdf_name}_ocr_cache.json')
        write_json_file(cache_path, ocr_result)

        return ocr_result

    def _extract_kv_from_text(self, tdef: Dict, text: str) -> Dict[str, str]:
        """从文本中提取 key_value 类型表格数据"""
        result = {}
        fields = tdef.get('fields', [])
        for f in fields:
            fname = f.get('field_name', '')
            desc = f.get('description', fname)
            if not desc:
                continue
            # 在文本中查找描述后面的值
            val = self._find_value_after_keyword(text, desc, f.get('type', 'text'))
            result[fname] = val if val is not None else ''
        return result

    def _extract_grid_from_text(self, tdef: Dict, text: str) -> Dict[str, Any]:
        """从文本中提取 data_grid 类型表格数据"""
        headers = tdef.get('headers', [])
        row_labels = tdef.get('row_labels', [])
        data_columns = tdef.get('data_columns', {})
        rows = []
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        # 尝试按行标签匹配行数据
        for label in row_labels:
            row_data = [''] * len(headers)
            for line in lines:
                if label in line:
                    # 提取行标签后面的数字/文本
                    after = line.split(label, 1)[-1].strip()
                    nums = re.findall(r'[-+]?\d+\.?\d*', after)
                    for col_name, col_idx in data_columns.items():
                        if col_idx < len(row_data):
                            # 尝试按列顺序填入数字
                            pass
                    # 简单策略：将找到的数字按列顺序填入
                    for i, num in enumerate(nums):
                        if i < len(row_data):
                            row_data[i] = num
                    break
            rows.append(row_data)
        return {'headers': headers, 'rows': rows}

    def _find_value_after_keyword(self, text: str, keyword: str,
                                   value_type: str = 'text') -> Optional[str]:
        """在文本中查找关键字后面的值"""
        if not text or not keyword:
            return None
        # 尝试多种模式匹配
        patterns = [
            rf'{re.escape(keyword)}\s*[:：]\s*(.+?)(?:\n|$)',
            rf'{re.escape(keyword)}\s+(.+?)(?:\n|$)',
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                val = m.group(1).strip()
                if val:
                    return val
        # 直接包含关键字时，取后面的内容
        idx = text.find(keyword)
        if idx >= 0:
            after = text[idx + len(keyword):idx + len(keyword) + 80].strip()
            val = after.split('\n')[0].strip().strip(':：').strip()
            if val:
                return val
        return None

    def compare_ocr_with_template(self, ocr_cache: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        逐字段比对 OCR 缓存与模板规则，返回异常列表。
        重点检查：
        - 发热模板的计算字段（电阻法温升、热电偶法温升）
        - 参数异常检测（室温、电压、电流等是否在合理范围）
        - 限值字段是否超标
        """
        errors = []
        if not ocr_cache or not self._current_template:
            return errors

        tmpl = self._current_template
        rules = tmpl.get('rules', [])
        tables_def = tmpl.get('tables', [])
        ocr_tables = ocr_cache.get('tables', {})
        limits = tmpl.get('limits', {})

        # 1. 逐规则比对
        for rule in rules:
            if rule.get('_comment') or not rule.get('type'):
                continue
            rule_type = rule.get('type', '')
            field_name = rule.get('field_name', '')
            unit = rule.get('unit', '')
            field_desc = self._get_field_desc(field_name)

            # 在 OCR 缓存中查找该字段的值
            ocr_value = self._find_field_in_ocr_cache(field_name, ocr_tables, tables_def)

            if rule_type == 'limit':
                limit = rule.get('limit')
                operator = rule.get('operator', '<=')
                if ocr_value is not None and limit is not None:
                    try:
                        num_val = float(ocr_value) if not isinstance(ocr_value, (int, float)) else ocr_value
                        if not check_limit(num_val, limit, operator):
                            errors.append({
                                'level': 'error',
                                'field_name': field_name,
                                'message': f'{field_desc}：{num_val}{unit} {operator} {limit}{unit}，超出标准限值',
                            })
                        else:
                            errors.append({
                                'level': 'info',
                                'field_name': field_name,
                                'message': f'{field_desc}：{num_val}{unit} {operator} {limit}{unit}，符合标准',
                            })
                    except (ValueError, TypeError):
                        errors.append({
                            'level': 'warning',
                            'field_name': field_name,
                            'message': f'{field_desc}：OCR 识别值 "{ocr_value}" 无法转换为数值',
                        })

            elif rule_type == 'tolerance':
                expected = rule.get('expected')
                if ocr_value is not None and expected is not None:
                    try:
                        num_val = float(ocr_value) if not isinstance(ocr_value, (int, float)) else ocr_value
                        tolerance = rule.get('tolerance', TOLERANCE.get('numeric', 5.0))
                        if not check_tolerance(num_val, expected, tolerance):
                            deviation = abs(num_val - expected)
                            errors.append({
                                'level': 'warning',
                                'field_name': field_name,
                                'message': f'{field_desc}：{num_val}{unit}，标准值 {expected}{unit}，偏差 {deviation:.1f}{unit}',
                            })
                        else:
                            errors.append({
                                'level': 'info',
                                'field_name': field_name,
                                'message': f'{field_desc}：{num_val}{unit}，标准值 {expected}{unit}，符合',
                            })
                    except (ValueError, TypeError):
                        errors.append({
                            'level': 'warning',
                            'field_name': field_name,
                            'message': f'{field_desc}：OCR 识别值 "{ocr_value}" 无法转换为数值',
                        })

            elif rule_type == 'calculation':
                formula = rule.get('formula', '')
                if ocr_value is not None and formula:
                    try:
                        num_val = float(ocr_value) if not isinstance(ocr_value, (int, float)) else ocr_value
                        calc_value = self._calculate_formula_from_ocr(formula, ocr_tables, tables_def)
                        if calc_value is not None:
                            calc_tol = rule.get('tolerance', TOLERANCE.get('calculation', 2.0))
                            if not check_tolerance(calc_value, num_val, calc_tol):
                                errors.append({
                                    'level': 'error',
                                    'field_name': field_name,
                                    'message': f'{field_desc}：记录值 {num_val}{unit}，按公式应为 {calc_value:.1f}{unit}，偏差 {abs(num_val - calc_value):.1f}{unit}，计算有误',
                                })
                            else:
                                errors.append({
                                    'level': 'info',
                                    'field_name': field_name,
                                    'message': f'{field_desc}：记录值 {num_val}{unit}，计算值 {calc_value:.1f}{unit}，一致',
                                })
                    except (ValueError, TypeError):
                        pass

        # 2. 发热模板专项：电阻法温升计算校验
        if tmpl.get('meta', {}).get('clause', '').find('发热') >= 0:
            errors.extend(self._check_heating_calculations(ocr_tables, tables_def, limits))

        # 3. 参数异常检测
        errors.extend(self._check_parameter_anomalies(ocr_tables, tables_def, limits))

        return errors

    def _find_field_in_ocr_cache(self, field_name: str,
                                  ocr_tables: Dict, tables_def: List) -> Optional[Any]:
        """在 OCR 缓存中查找指定字段的值"""
        for tdef in tables_def:
            tname = tdef.get('table_name', '')
            tdata = ocr_tables.get(tname, {})
            if tdef.get('type') == 'key_value':
                if isinstance(tdata, dict) and field_name in tdata:
                    return tdata[field_name]
            # data_grid 中按 data_columns 查找
            elif tdef.get('type') == 'data_grid':
                data_columns = tdef.get('data_columns', {})
                for col_name, col_idx in data_columns.items():
                    if col_name == field_name or field_name.startswith(col_name):
                        # 在行数据中查找
                        if isinstance(tdata, dict):
                            rows = tdata.get('rows', [])
                            for row in rows:
                                if col_idx < len(row) and row[col_idx]:
                                    return row[col_idx]
        return None

    def _calculate_formula_from_ocr(self, formula: str,
                                     ocr_tables: Dict, tables_def: List) -> Optional[float]:
        """使用 OCR 缓存数据计算公式"""
        try:
            local_vars = {}
            # 收集所有 OCR 数值字段
            for tdef in tables_def:
                tname = tdef.get('table_name', '')
                tdata = ocr_tables.get(tname, {})
                if tdef.get('type') == 'key_value' and isinstance(tdata, dict):
                    for k, v in tdata.items():
                        try:
                            local_vars[k] = float(v)
                        except (ValueError, TypeError):
                            pass
                elif tdef.get('type') == 'data_grid':
                    data_columns = tdef.get('data_columns', {})
                    if isinstance(tdata, dict):
                        rows = tdata.get('rows', [])
                        for row in rows:
                            for col_name, col_idx in data_columns.items():
                                if col_idx < len(row) and row[col_idx]:
                                    try:
                                        local_vars[col_name] = float(row[col_idx])
                                    except (ValueError, TypeError):
                                        pass
            result = eval(formula, {}, local_vars)
            if isinstance(result, (int, float)):
                return float(result)
        except Exception:
            pass
        return None

    def _check_heating_calculations(self, ocr_tables: Dict,
                                     tables_def: List,
                                     limits: Dict) -> List[Dict[str, Any]]:
        """
        发热模板专项校验：
        - 电阻法温升：△t = (R2-R1)/R1 × (234.5+t1) - (t2-t1)
        - 热电偶法温升：△t = 热态温度 - 室温
        """
        errors = []
        # 查找电阻法温升数据
        res_data = ocr_tables.get('resistance_measurement', {})
        rise_data = ocr_tables.get('temperature_rise_resistance', {})
        thermo_data = ocr_tables.get('thermocouple_results', {})

        # 电阻法温升校验：检查冷态/热态电阻与温升是否匹配
        if isinstance(res_data, dict) and isinstance(rise_data, dict):
            res_rows = res_data.get('rows', [])
            rise_rows = rise_data.get('rows', [])
            # 简单校验：温升值应在合理范围（0-150K）
            max_rise = limits.get('stator_max', 80.0)
            for row in rise_rows:
                for val_str in row[1:]:  # 跳过电压列
                    try:
                        val = float(val_str)
                        if val > max_rise * 1.5:  # 超过限值 150% 时报错
                            errors.append({
                                'level': 'error',
                                'field_name': 'temperature_rise',
                                'message': f'电阻法温升 {val}K 超过限值 {max_rise}K 的 1.5 倍，参数异常',
                            })
                        elif val < 0:
                            errors.append({
                                'level': 'error',
                                'field_name': 'temperature_rise',
                                'message': f'电阻法温升 {val}K 为负值，数据异常',
                            })
                    except (ValueError, TypeError):
                        pass

        # 热电偶法校验：热态温度应合理
        if isinstance(thermo_data, dict):
            rows = thermo_data.get('rows', [])
            if len(rows) >= 2:
                hot_row = rows[0]  # 热态温度行
                rise_row = rows[1]  # 温升行
                for val_str in hot_row[1:]:  # 跳过部位列
                    try:
                        val = float(val_str)
                        if val > 150:
                            errors.append({
                                'level': 'warning',
                                'field_name': 'thermocouple_temp',
                                'message': f'热电偶法热态温度 {val}°C 超过 150°C，参数异常',
                            })
                    except (ValueError, TypeError):
                        pass

        return errors

    def _check_parameter_anomalies(self, ocr_tables: Dict,
                                    tables_def: List,
                                    limits: Dict) -> List[Dict[str, Any]]:
        """参数异常检测：检查关键参数是否在合理范围内"""
        errors = []
        # 检查封面信息中的室温
        cover = ocr_tables.get('cover_info', {})
        if isinstance(cover, dict):
            # 检查室温
            room_temp = cover.get('t2_room', '')
            if room_temp:
                try:
                    temp = float(room_temp)
                    if temp < 15 or temp > 35:
                        errors.append({
                            'level': 'warning',
                            'field_name': 't2_room',
                            'message': f'室温 {temp}°C 不在合理范围（15-35°C）',
                        })
                except (ValueError, TypeError):
                    pass

        # 检查输入输出参数表
        io_data = ocr_tables.get('input_output_params', {})
        if isinstance(io_data, dict):
            rows = io_data.get('rows', [])
            for row in rows:
                # 检查电压（列2）、电流（列4）
                if len(row) > 4:
                    try:
                        voltage = float(row[2]) if row[2] else 0
                        if voltage > 0 and (voltage < 100 or voltage > 500):
                            errors.append({
                                'level': 'warning',
                                'field_name': 'voltage',
                                'message': f'电压 {voltage}V 不在合理范围（100-500V）',
                            })
                    except (ValueError, TypeError):
                        pass
                    try:
                        current = float(row[4]) if row[4] else 0
                        if current > 0 and current > 50:
                            errors.append({
                                'level': 'warning',
                                'field_name': 'current',
                                'message': f'电流 {current}A 超过 50A，参数异常',
                            })
                    except (ValueError, TypeError):
                        pass

        return errors


if __name__ == "__main__":
    checker = ReportChecker()
    print(f"OCR 引擎可用: {checker.is_ocr_available()}")
    print(f"引擎详情:\n{checker.get_ocr_engine_info()}")
    print("core_checker.py 模块加载完成")
