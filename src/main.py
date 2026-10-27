"""
电动工具测试报告校验工具
主入口文件

运行方式：
    1. 双击 run.bat 启动
    2. 或命令行执行: python main.py

技术特点：
    - 纯本地运行，不联网
    - 模板驱动识别，支持自定义字段和规则
    - 支持 PDF / Word / 图片格式报告
    - 使用 PyMuPDF 渲染 PDF，规避加密读取风险
    - 多 OCR 引擎自动级联（PaddleOCR / RapidOCR / Tesseract）
    - 支持多种测试类型切换（温升/电气强度/接地/泄漏/功率/EMC 等）
"""

import os
import sys

import asset_paths


def _find_onnx_capi_dir():
    """查找 onnxruntime capi DLL 目录（运行时目录优先，兼容旧项目内目录）。"""
    import glob as _glob
    for root in (asset_paths.python_dir(),
                 os.path.join(asset_paths.PROJECT_ROOT, "python")):
        for lib_name in ("Lib", "lib"):
            pattern = os.path.join(root, lib_name, "site-packages",
                                   "onnxruntime", "capi")
            if os.path.isdir(pattern):
                return pattern
            candidates = _glob.glob(os.path.join(
                root, "python", lib_name, "python3.*", "site-packages",
                "onnxruntime", "capi"))
            if candidates:
                return candidates[0]
    return None


def _prepare_runtime_env():
    """初始化运行时环境：把本地依赖目录加入 PATH/DLL 搜索路径。"""
    tesseract_dir = asset_paths.tesseract_dir()
    deps_dir = asset_paths.deps_dir()

    for p in (tesseract_dir, deps_dir):
        if p and p not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")

    onnx_capi = _find_onnx_capi_dir()
    if onnx_capi and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(onnx_capi)

    if os.path.isdir(os.path.join(tesseract_dir, "tessdata")):
        os.environ["TESSDATA_PREFIX"] = os.path.join(tesseract_dir, "tessdata")


def main():
    """
    主函数入口
    
    Example:
        >>> if __name__ == "__main__":
        ...     main()
    """
    _prepare_runtime_env()
    try:
        from gui_app import run_app
        run_app()
    except ImportError as e:
        print(f"导入模块失败: {e}")
        print("请确保已安装以下依赖:")
        print("  - PyQt6")
        print("  - PyMuPDF (fitz)")
        print("  - PaddleOCR")
        print("  - Pillow")
        print("  - numpy")
        sys.exit(1)
    except Exception as e:
        print(f"程序运行出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
