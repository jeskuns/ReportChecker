"""打包 ReportChecker 为单文件 exe（无需系统安装 Python）"""
import os
import sys
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(ROOT, "python", "python.exe")

if not os.path.exists(PYTHON):
    raise FileNotFoundError(f"未找到 {PYTHON}，请先准备嵌入式 Python。")

ICON = os.path.join(ROOT, "logo.ico") if os.path.exists(os.path.join(ROOT, "logo.ico")) else None

args = [
    PYTHON, "-m", "PyInstaller",
    "--onefile",
    "--windowed",
    "--name", "ReportChecker",
    "--add-data", f"src{os.pathsep}src",
    "--add-data", f"deps{os.pathsep}deps",
    "--add-data", f"templates{os.pathsep}templates",
    "--add-data", f"python{os.pathsep}python",
    "--add-data", f"logo.ico{os.pathsep}.",
    "--add-data", f"logo.png{os.pathsep}.",
    "--hidden-import", "PyQt6.sip",
    "--hidden-import", "PyQt6.QtCore",
    "--hidden-import", "PyQt6.QtGui",
    "--hidden-import", "PyQt6.QtWidgets",
    "--hidden-import", "fitz",
    "--hidden-import", "PIL",
    "--hidden-import", "paddle",
    "--hidden-import", "onnxruntime",
    "--hidden-import", "numpy",
    "--clean",
]
if ICON:
    args += ["--icon", ICON]

args.append(os.path.join(ROOT, "run.py"))

print("Running:", " ".join(args))
subprocess.run(args, check=True)
print("\n✅ 打包完成：dist/ReportChecker.exe")
