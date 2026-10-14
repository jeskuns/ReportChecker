"""
ReportChecker 启动器（便携模式）

负责：
  1. 配置本地依赖路径（deps/tesseract、onnxruntime DLL、TESSDATA）
  2. 捕获启动异常并以 MessageBox 提示（避免黑框一闪而过看不到错误）
  3. 启动 GUI

运行: 双击 run.bat
"""
import os
import sys
import traceback
import glob as _glob


def _find_root():
    """定位项目根目录：run.py 所在目录即项目根目录。"""
    return os.path.dirname(os.path.abspath(__file__))


def _find_onnx_capi_dir(root):
    """查找 onnxruntime capi DLL 目录（兼容不同 Python 版本和平台路径）。"""
    for lib_name in ("Lib", "lib"):
        path = os.path.join(root, "python", lib_name, "site-packages", "onnxruntime", "capi")
        if os.path.isdir(path):
            return path
        candidates = _glob.glob(os.path.join(
            root, "python", lib_name, "python3.*", "site-packages", "onnxruntime", "capi"))
        if candidates:
            return candidates[0]
    return None


def _prepare_env():
    root = _find_root()
    src_dir = os.path.join(root, "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    tesseract_dir = os.path.join(root, "deps", "tesseract")
    deps_dir = os.path.join(root, "deps")
    for p in (tesseract_dir, deps_dir):
        if p and p not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")

    onnx_capi = _find_onnx_capi_dir(root)
    if onnx_capi and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(onnx_capi)

    if os.path.isdir(os.path.join(tesseract_dir, "tessdata")):
        os.environ["TESSDATA_PREFIX"] = os.path.join(tesseract_dir, "tessdata")


def _notify(title, message):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
    except Exception:
        sys.stderr.write(f"{title}: {message}\n")


def main():
    _prepare_env()
    try:
        from gui_app import run_app
        run_app()
    except Exception as e:
        _notify("ReportChecker 启动失败", f"{e}\n\n{traceback.format_exc()}")


if __name__ == "__main__":
    main()
