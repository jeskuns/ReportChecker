"""
ReportChecker 启动器（便携模式）

负责：
  1. 配置本地依赖路径（运行时目录优先，兼容项目内旧目录）
  2. 依赖缺失时引导一键安装（国内镜像）
  3. 捕获启动异常并以 MessageBox 提示（避免黑框一闪而过看不到错误）

运行: 双击 run.bat
"""

import os
import sys
import traceback
import subprocess
import glob as _glob

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(ROOT, 'src')
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import asset_paths  # noqa: E402

CORE_MODULES = {'PyQt6', 'fitz', 'numpy', 'PIL', 'scipy', 'matplotlib',
                'shapely', 'skimage', 'win32api', 'requests',
                'rapidocr_onnxruntime', 'docx'}


def _find_onnx_capi_dir():
    """查找 onnxruntime capi DLL 目录（运行时目录 / 项目内旧目录）。"""
    roots = [asset_paths.python_dir(), os.path.join(ROOT, 'python')]
    for root in roots:
        for lib_name in ('Lib', 'lib'):
            path = os.path.join(root, lib_name, 'site-packages',
                                'onnxruntime', 'capi')
            if os.path.isdir(path):
                return path
            candidates = _glob.glob(os.path.join(
                root, lib_name, 'python3.*', 'site-packages',
                'onnxruntime', 'capi'))
            if candidates:
                return candidates[0]
    return None


def _prepare_env():
    for p in (asset_paths.tesseract_dir(), asset_paths.deps_dir()):
        if p and p not in os.environ.get('PATH', '').split(os.pathsep):
            os.environ['PATH'] = p + os.pathsep + os.environ.get('PATH', '')

    onnx_capi = _find_onnx_capi_dir()
    if onnx_capi and hasattr(os, 'add_dll_directory'):
        try:
            os.add_dll_directory(onnx_capi)
        except OSError:
            pass

    tessdata = os.path.join(asset_paths.tesseract_dir(), 'tessdata')
    if os.path.isdir(tessdata):
        os.environ['TESSDATA_PREFIX'] = tessdata


def _notify(title, message, flags=0x10):
    try:
        import ctypes
        return ctypes.windll.user32.MessageBoxW(0, message, title, flags)
    except Exception:
        sys.stderr.write(f'{title}: {message}\n')
        return 0


def _install_dialogue(exc) -> bool:
    name = (getattr(exc, 'name', '') or '').split('.')[0]
    if name not in CORE_MODULES:
        return False
    choice = _notify(
        'ReportChecker 缺少运行依赖',
        f'缺少组件：{name}\n\n'
        '是否立即从国内镜像（清华 TUNA / 阿里云 / ModelScope）'
        '一键安装依赖与 OCR 模型？\n\n'
        '安装过程需要联网，约 1–10 分钟，取决于网络。',
        0x04 | 0x20)  # MB_YESNO | MB_ICONQUESTION
    if choice != 6:  # IDYES
        return False
    script = os.path.join(ROOT, 'tools', 'install_env.py')
    proc = subprocess.run([sys.executable, script, '--all'], cwd=ROOT)
    return proc.returncode == 0


def main():
    _prepare_env()
    try:
        from gui_app import run_app
        run_app()
    except ImportError as exc:
        if _install_dialogue(exc):
            try:
                import importlib
                importlib.invalidate_caches()
                from gui_app import run_app
                run_app()
                return
            except Exception as retry_exc:
                _notify('ReportChecker 启动失败',
                        f'{retry_exc}\n\n{traceback.format_exc()}')
        else:
            _notify('ReportChecker 无法启动',
                    f'缺少组件：{exc}\n\n'
                    '可双击 setup_env.bat，或在项目目录执行：\n'
                    'python tools\\install_env.py --all')
    except Exception as exc:
        _notify('ReportChecker 启动失败', f'{exc}\n\n{traceback.format_exc()}')


if __name__ == '__main__':
    main()
