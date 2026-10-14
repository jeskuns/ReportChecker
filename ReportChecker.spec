# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\Administrator\\Documents\\trae_projects\\ReportChecker\\run.py'],
    pathex=[],
    binaries=[],
    datas=[('src', 'src'), ('deps', 'deps'), ('templates', 'templates'), ('python', 'python'), ('logo.ico', '.'), ('logo.png', '.')],
    hiddenimports=['PyQt6.sip', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'fitz', 'PIL', 'paddle', 'onnxruntime', 'numpy'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ReportChecker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\Users\\Administrator\\Documents\\trae_projects\\ReportChecker\\logo.ico'],
)
