"""
运行时资源路径管理

项目目录只保留源码（轻量化），大型资源（Python 环境、OCR 模型、Tesseract、
标准报告 PDF）默认存放在外部运行目录：

    %LOCALAPPDATA%\\ReportChecker\\runtime

可用环境变量 REPORTCHECKER_HOME 覆盖，或在项目根目录 runtime_config.json
中写入 {"runtime_root": "D:\\\\ReportChecker\\\\runtime"}。

旧版本把资源放在项目内（python/、deps/、models/、reports/），这里保留回退：
运行目录存在时优先使用运行目录，否则继续使用项目内旧目录。
"""

import json
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(PROJECT_ROOT, 'runtime_config.json')


def default_runtime_root() -> str:
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'ReportChecker', 'runtime')


def runtime_root() -> str:
    env = (os.environ.get('REPORTCHECKER_HOME') or '').strip()
    if env:
        return os.path.abspath(os.path.expanduser(env))
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            saved = (json.load(f).get('runtime_root') or '').strip()
        if saved:
            return os.path.abspath(os.path.expanduser(saved))
    except (OSError, ValueError):
        pass
    return default_runtime_root()


def set_runtime_root(path: str) -> str:
    path = os.path.abspath(os.path.expanduser(path))
    data = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
    data['runtime_root'] = path
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def runtime_path(*parts: str) -> str:
    return os.path.join(runtime_root(), *parts)


def _resolve(subdir: str) -> str:
    """运行目录优先，其次回退到项目内旧目录（兼容未迁移的安装）。"""
    candidate = runtime_path(subdir)
    if os.path.isdir(candidate):
        return candidate
    legacy = os.path.join(PROJECT_ROOT, subdir)
    if os.path.isdir(legacy):
        return legacy
    return candidate


def python_dir() -> str:
    return _resolve('python')


def python_exe() -> str:
    return os.path.join(python_dir(), 'python.exe')


def deps_dir() -> str:
    return _resolve('deps')


def tesseract_dir() -> str:
    return os.path.join(deps_dir(), 'tesseract')


def models_dir() -> str:
    return _resolve('models')


def ocr_models_dir() -> str:
    return os.path.join(models_dir(), 'ocr')


def reports_dir() -> str:
    return _resolve('reports')


def ensure_runtime_dirs() -> None:
    for sub in ('python', 'deps', 'models/ocr/rapid',
                'models/ocr/paddle_det', 'models/ocr/paddle_rec', 'reports'):
        os.makedirs(runtime_path(*sub.split('/')), exist_ok=True)
