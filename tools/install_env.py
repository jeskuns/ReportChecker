"""命令行一键安装（无界面，可在 PyQt6 缺失时运行）

用法：
    python tools/install_env.py --all
    python tools/install_env.py --models-only
    python tools/install_env.py --status
"""

import argparse
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, OSError):
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

import asset_paths  # noqa: E402
import env_installer  # noqa: E402


def _log(msg):
    print(msg, flush=True)


def _progress(frac, msg):
    bar = int(frac * 30)
    print(f'\r[{"#" * bar}{"." * (30 - bar)}] {frac * 100:5.1f}%  {msg}',
          end='', flush=True)
    if frac >= 1.0:
        print()


def _print_status():
    print(f'运行目录：{asset_paths.runtime_root()}\n')
    for item in env_installer.check_environment():
        mark = '✓' if item['ok'] else ('✗' if item['required'] else '○')
        print(f"  {mark} {item['label']}：{item['detail']}")


def main():
    parser = argparse.ArgumentParser(description='ReportChecker 环境与模型安装')
    parser.add_argument('--status', action='store_true', help='仅查看状态')
    parser.add_argument('--all', action='store_true', help='安装依赖包和全部模型')
    parser.add_argument('--models-only', action='store_true', help='只安装 OCR 模型')
    parser.add_argument('--no-paddle', action='store_true', help='不安装 PaddleOCR')
    parser.add_argument('--force', action='store_true', help='强制重新下载模型')
    args = parser.parse_args()

    _print_status()
    if args.status:
        return 0

    if args.models_only:
        env_installer.install_rapid_models(log=_log, progress=_progress,
                                           force=args.force)
        if not args.no_paddle:
            try:
                env_installer.install_paddle_models(log=_log, progress=_progress,
                                                    force=args.force)
            except Exception as exc:
                _log(f'PaddleOCR 模型安装失败（不影响 RapidOCR）：{exc}')
        return 0

    try:
        env_installer.install(include_paddle=not args.no_paddle,
                              force_models=args.force,
                              log=_log, progress=_progress)
        return 0
    except Exception as exc:
        _log(f'\n安装失败：{exc}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
