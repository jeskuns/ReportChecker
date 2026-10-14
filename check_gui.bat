@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0python\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [错误] 未找到 python\python.exe
    pause
    exit /b 1
)

"%PYTHON_EXE%" -B -c "
import os, sys, gui_app, traceback
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))
try:
    import gui_app
    msg = '加载文件: ' + gui_app.__file__ + '\n' + 'TEXT_MUTED 使用: ' + str('TEXT_MUTED' in gui_app.__dict__)
    print(msg)
except Exception as e:
    print('加载失败: ' + str(e))
    print(traceback.format_exc())
"

pause
