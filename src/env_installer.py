"""
环境与模型一键安装

只依赖标准库，可在 PyQt6 缺失时由 tools/install_env.py 直接调用。

安装内容：
  1. Python 依赖包（pip，清华 TUNA / 阿里云 PyPI）
  2. RapidOCR ONNX 模型（ModelScope）
  3. PaddleOCR 增强（可选：paddlepaddle + paddleocr + 百度 BOS 模型）

资源统一安装到 asset_paths.runtime_root()，项目目录保持轻量。
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request

import asset_paths
import mirrors


class InstallCancelled(Exception):
    pass


# (import 名, pip 包名, 说明)
CORE_PACKAGES = [
    ('PyQt6', 'PyQt6>=6.6.0', '界面框架'),
    ('fitz', 'PyMuPDF>=1.23.10', 'PDF 渲染与文字提取'),
    ('numpy', 'numpy>=1.24.3', '数值计算'),
    ('PIL', 'Pillow>=10.1.0', '图像处理'),
    ('scipy', 'scipy>=1.11.4', '科学计算'),
    ('matplotlib', 'matplotlib>=3.8.2', '图表绘制'),
    ('shapely', 'shapely>=2.0.2', '几何计算'),
    ('skimage', 'scikit-image>=0.22.0', '图像增强'),
    ('win32api', 'pywin32>=306', 'Windows 窗口与 COM'),
    ('requests', 'requests>=2.31.0', 'AI 接口调用'),
    ('rapidocr_onnxruntime', 'rapidocr-onnxruntime>=1.4.0', '轻量中文 OCR'),
    ('pytesseract', 'pytesseract>=0.3.10', 'Tesseract 调用封装'),
    ('docx', 'python-docx>=1.1.0', 'Word 读取'),
]

PADDLE_PACKAGES = [
    ('paddleocr', 'paddleocr>=3.0.0', 'PaddleOCR 识别'),
    ('paddle', 'paddlepaddle>=3.0.0', 'PaddlePaddle 推理后端'),
]

RAPID_MODELS = [
    ('det/ch_PP-OCRv4_det_mobile.onnx',
     'ch_PP-OCRv4_det_infer.onnx', 4745517),
    ('rec/ch_PP-OCRv4_rec_mobile.onnx',
     'ch_PP-OCRv4_rec_infer.onnx', 10857958),
    ('cls/ch_ppocr_mobile_v2.0_cls_mobile.onnx',
     'ch_ppocr_mobile_v2.0_cls_infer.onnx', 585532),
]

PADDLE_MODELS = [
    ('PP-OCRv5_mobile_det_infer.tar', 'paddle_det', 4935680),
    ('PP-OCRv5_mobile_rec_infer.tar', 'paddle_rec', 16834560),
]


# ───────────────────────── 通用工具 ─────────────────────────

def _creation_flags() -> int:
    return getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def _module_ok(module: str) -> bool:
    try:
        importlib.invalidate_caches()
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def _file_ok(path: str, min_size: int = 1024) -> bool:
    try:
        return os.path.isfile(path) and os.path.getsize(path) >= min_size
    except OSError:
        return False


def _noop(_msg: str) -> None:
    pass


def _noop_progress(_fraction: float, _msg: str) -> None:
    pass


def _check_cancel(cancel) -> None:
    if cancel is not None and cancel():
        raise InstallCancelled('已取消')


def _safe_extract(tar: tarfile.TarFile, dest: str) -> None:
    dest_abs = os.path.abspath(dest)
    for member in tar.getmembers():
        target = os.path.abspath(os.path.join(dest, member.name))
        if not target.startswith(dest_abs + os.sep):
            raise RuntimeError(f'压缩包路径异常: {member.name}')
    tar.extractall(dest)


# ───────────────────────── 状态检测 ─────────────────────────

def _rapid_model_paths():
    root = os.path.join(asset_paths.ocr_models_dir(), 'rapid')
    return [os.path.join(root, name) for _src, name, _size in RAPID_MODELS]


def missing_core_packages():
    return [(mod, spec) for mod, spec, _desc in CORE_PACKAGES if not _module_ok(mod)]


def missing_paddle_packages():
    return [(mod, spec) for mod, spec, _desc in PADDLE_PACKAGES
            if not _module_ok(mod)]


def rapid_models_ready() -> bool:
    return all(_file_ok(p) for p in _rapid_model_paths())


def paddle_models_ready() -> bool:
    det = os.path.join(asset_paths.ocr_models_dir(), 'paddle_det')
    rec = os.path.join(asset_paths.ocr_models_dir(), 'paddle_rec')
    return _file_ok(os.path.join(det, 'inference.pdiparams')) and \
        _file_ok(os.path.join(rec, 'inference.pdiparams'))


def tesseract_ready() -> bool:
    tess = asset_paths.tesseract_dir()
    return os.path.isfile(os.path.join(tess, 'tesseract.exe')) and \
        os.path.isdir(os.path.join(tess, 'tessdata'))


def report_pdf_count() -> int:
    root = asset_paths.reports_dir()
    try:
        return len([f for f in os.listdir(root) if f.lower().endswith('.pdf')])
    except OSError:
        return 0


def check_environment() -> list:
    """返回各组资源状态，供设置界面展示。"""
    missing_core = missing_core_packages()
    missing_paddle = missing_paddle_packages()
    rapid_ok = rapid_models_ready()
    paddle_ok = paddle_models_ready() and not missing_paddle
    reports = report_pdf_count()
    items = [
        {
            'key': 'python',
            'label': 'Python 运行时',
            'required': True,
            'ok': os.path.isfile(asset_paths.python_exe()) or bool(sys.executable),
            'detail': sys.executable,
        },
        {
            'key': 'packages',
            'label': 'Python 依赖包',
            'required': True,
            'ok': not missing_core,
            'detail': '全部就绪' if not missing_core else
                      '缺少 ' + '、'.join(mod for mod, _ in missing_core),
        },
        {
            'key': 'rapid',
            'label': 'RapidOCR 模型（必需）',
            'required': True,
            'ok': rapid_ok,
            'detail': '3 个 ONNX 模型已就绪' if rapid_ok else
                      '缺少 RapidOCR 模型（约 15 MB）',
        },
        {
            'key': 'paddle',
            'label': 'PaddleOCR 增强（可选）',
            'required': False,
            'ok': paddle_ok,
            'detail': '已安装' if paddle_ok else
                      '未安装（约 300–600 MB，可大幅提升扫描件精度）',
        },
        {
            'key': 'tesseract',
            'label': 'Tesseract 备用引擎（可选）',
            'required': False,
            'ok': tesseract_ready(),
            'detail': '已就绪' if tesseract_ready() else
                      '未安装（不影响使用，RapidOCR 可替代）',
        },
        {
            'key': 'reports',
            'label': '标准报告 PDF',
            'required': False,
            'ok': reports > 0,
            'detail': f'{reports} 个模板' if reports else '未找到（随项目附带）',
        },
    ]
    return items


# ───────────────────────── 下载 ─────────────────────────

def download(urls, dest: str, expected_size: int = 0,
             progress=None, log=_noop, cancel=None, label: str = '') -> str:
    """按顺序尝试多个镜像；支持断点续传。

    urls: [(镜像名, url), ...]
    progress: callable(fraction, message)
    """
    progress = progress or _noop_progress
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + '.part'
    errors = []

    for name, url in urls:
        _check_cancel(cancel)
        log(f'下载 {label or os.path.basename(dest)} ← {name}')
        try:
            existing = os.path.getsize(part) if os.path.exists(part) else 0
            if expected_size and existing >= expected_size:
                os.replace(part, dest)
                progress(1.0, f'{label} 已完成')
                return dest

            req = urllib.request.Request(
                url, headers={'User-Agent': 'ReportChecker/2.0'})
            if existing:
                req.add_header('Range', f'bytes={existing}-')

            with urllib.request.urlopen(req, timeout=60) as resp:
                mode = 'ab' if existing and resp.status == 206 else 'wb'
                if mode == 'wb':
                    existing = 0
                total = expected_size
                length = resp.headers.get('Content-Length')
                if length and length.isdigit():
                    total = existing + int(length) if mode == 'ab' else int(length)
                done = existing
                with open(part, mode) as f:
                    while True:
                        _check_cancel(cancel)
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        frac = (done / total) if total else 0.0
                        progress(min(frac, 0.999),
                                 f'{label} {done / 1048576:.1f}'
                                 f'/{total / 1048576:.1f} MB' if total else label)

            size = os.path.getsize(part)
            if expected_size and size < expected_size:
                raise IOError(f'文件不完整（{size}/{expected_size} 字节）')
            os.replace(part, dest)
            progress(1.0, f'{label} 下载完成')
            return dest
        except InstallCancelled:
            raise
        except Exception as exc:  # 换下一个镜像
            errors.append(f'{name}: {exc}')
            log(f'  {name} 失败：{exc}')

    raise RuntimeError(f'{label or dest} 下载失败：' + '；'.join(errors))


# ───────────────────────── pip 安装 ─────────────────────────

def _ensure_pip(log=_noop, cancel=None) -> None:
    if _module_ok('pip'):
        return
    log('未检测到 pip，正在从阿里云安装 pip...')
    tmp = os.path.join(tempfile.gettempdir(), 'reportchecker_get-pip.py')
    download(mirrors.GET_PIP, tmp, log=log, cancel=cancel, label='get-pip.py')
    subprocess.run([sys.executable, tmp, '-i', mirrors.PYPI_INDEXES[0][1]],
                   check=True, creationflags=_creation_flags())
    importlib.invalidate_caches()


def _run_pip(specs, log, cancel, index_url: str) -> bool:
    cmd = [
        sys.executable, '-m', 'pip', 'install', '--no-input',
        '--disable-pip-version-check', '--no-warn-script-location',
        '--retries', '3', '--timeout', '60',
        '--upgrade-strategy', 'only-if-needed',
        '-i', index_url,
    ] + list(specs)
    log('执行：pip install ' + ' '.join(specs))
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8', errors='replace',
        creationflags=_creation_flags())
    try:
        for line in proc.stdout:
            _check_cancel(cancel)
            line = line.rstrip()
            if line:
                log(line)
        proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
    importlib.invalidate_caches()
    return proc.returncode == 0


def install_packages(log=_noop, progress=_noop_progress, cancel=None,
                     include_paddle: bool = False, force: bool = False) -> bool:
    _ensure_pip(log, cancel)
    missing = missing_core_packages()
    if force:
        missing = [(mod, spec) for mod, spec, _ in CORE_PACKAGES]
    if include_paddle:
        missing += missing_paddle_packages()
    if not missing:
        log('Python 依赖包已齐全，跳过。')
        progress(1.0, '依赖包已就绪')
        return True

    specs = [spec for _mod, spec in missing]
    log(f'需要安装 {len(specs)} 个依赖包：' + '、'.join(specs[:6]) +
        ('...' if len(specs) > 6 else ''))
    for idx, (name, index_url) in enumerate(mirrors.PYPI_INDEXES):
        if _run_pip(specs, log, cancel, index_url):
            log(f'依赖包安装完成（{name}）')
            _post_install_hooks(log)
            progress(1.0, '依赖包已就绪')
            return True
        log(f'{name} 源安装失败，尝试下一个镜像')
    raise RuntimeError('依赖包安装失败，请检查网络后重试')


def _post_install_hooks(log) -> None:
    """pywin32 在嵌入式 Python 下需要注册 COM。"""
    script = os.path.join(os.path.dirname(sys.executable),
                          'Scripts', 'pywin32_postinstall.py')
    if os.path.exists(script):
        try:
            subprocess.run([sys.executable, script, '-install', '-silent'],
                           timeout=120, creationflags=_creation_flags(),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            log(f'pywin32 注册提示：{exc}')


# ───────────────────────── 模型安装 ─────────────────────────

def install_rapid_models(log=_noop, progress=_noop_progress, cancel=None,
                         force: bool = False) -> bool:
    root = os.path.join(asset_paths.ocr_models_dir(), 'rapid')
    total = len(RAPID_MODELS)
    for i, (remote, local, size) in enumerate(RAPID_MODELS):
        dest = os.path.join(root, local)
        if not force and _file_ok(dest, size):
            log(f'{local} 已存在，跳过')
            progress((i + 1) / total, local)
            continue

        def _p(frac, msg, _i=i):
            progress((_i + frac) / total, msg)

        download([('ModelScope', mirrors.MODELSCOPE_RAPID_BASE + remote)],
                 dest, expected_size=size, progress=_p, log=log,
                 cancel=cancel, label=local)
    log('RapidOCR 模型已就绪')
    return True


def install_paddle_models(log=_noop, progress=_noop_progress, cancel=None,
                          force: bool = False) -> bool:
    ocr_root = asset_paths.ocr_models_dir()
    total = len(PADDLE_MODELS)
    with tempfile.TemporaryDirectory(prefix='rc_paddle_') as tmp:
        for i, (remote, subdir, size) in enumerate(PADDLE_MODELS):
            target = os.path.join(ocr_root, subdir)
            if not force and _file_ok(os.path.join(target, 'inference.pdiparams')):
                log(f'{subdir} 已存在，跳过')
                progress((i + 1) / total, subdir)
                continue

            tar_path = os.path.join(tmp, remote)

            def _p(frac, msg, _i=i):
                progress((_i + frac) / total, msg)

            download([('百度 BOS', mirrors.PADDLE_BOS_BASE + remote)],
                     tar_path, expected_size=size, progress=_p, log=log,
                     cancel=cancel, label=remote)
            extract_dir = os.path.join(tmp, subdir + '_x')
            os.makedirs(extract_dir, exist_ok=True)
            with tarfile.open(tar_path) as tar:
                _safe_extract(tar, extract_dir)
            source = extract_dir
            entries = os.listdir(extract_dir)
            if len(entries) == 1 and os.path.isdir(
                    os.path.join(extract_dir, entries[0])):
                source = os.path.join(extract_dir, entries[0])
            os.makedirs(target, exist_ok=True)
            for name in os.listdir(source):
                shutil.copy2(os.path.join(source, name),
                             os.path.join(target, name))
            os.remove(tar_path)
    log('PaddleOCR 模型已就绪')
    return True


# ───────────────────────── 总调度 ─────────────────────────

def install(include_paddle: bool = True, force_models: bool = False,
            log=_noop, progress=_noop_progress, cancel=None) -> None:
    """一键安装/修复。progress: callable(0..1, message)"""
    asset_paths.ensure_runtime_dirs()
    steps = [('deps', 0.55), ('rapid', 0.15)]
    if include_paddle:
        steps.append(('paddle', 0.30))
    total_weight = sum(w for _k, w in steps)
    base = 0.0

    for key, weight in steps:
        _check_cancel(cancel)
        span = weight / total_weight

        def _p(frac, msg, _base=base, _span=span):
            progress(_base + _span * frac, msg)

        if key == 'deps':
            install_packages(log=log, progress=_p, cancel=cancel,
                             include_paddle=include_paddle)
        elif key == 'rapid':
            install_rapid_models(log=log, progress=_p, cancel=cancel,
                                 force=force_models)
        elif key == 'paddle':
            install_paddle_models(log=log, progress=_p, cancel=cancel,
                                  force=force_models)
        base += span

    progress(1.0, '全部完成')
    log('环境与模型安装完成，重启应用后生效。')


def total_download_size_text(include_paddle: bool = True) -> str:
    mb = sum(size for _r, _l, size in RAPID_MODELS) / 1048576
    if include_paddle:
        mb += sum(size for _r, _s, size in PADDLE_MODELS) / 1048576
    return f'{mb:.1f} MB（模型）+ pip 依赖包'
