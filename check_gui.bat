@echo off
chcp 65001 >nul
cd /d "%~dp0"

if "%REPORTCHECKER_HOME%"=="" (
    set "RT=%LOCALAPPDATA%\ReportChecker\runtime"
) else (
    set "RT=%REPORTCHECKER_HOME%"
)

set "PYTHON_EXE=%~dp0python\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%RT%\python\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [错误] 未找到 Python 运行时，请先双击 setup_env.bat
    pause
    exit /b 1
)

"%PYTHON_EXE%" -B -c "import sys,os; sys.path.insert(0, os.path.join(os.getcwd(),'src')); import gui_app; print('加载成功:', gui_app.__file__)"

pause
