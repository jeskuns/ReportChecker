@echo off
chcp 65001 >nul
title ReportChecker
color 0A

cd /d "%~dp0"

if "%REPORTCHECKER_HOME%"=="" (
    set "RT=%LOCALAPPDATA%\ReportChecker\runtime"
) else (
    set "RT=%REPORTCHECKER_HOME%"
)

echo.
echo ============================================
echo     ReportChecker - Test Report Validator
echo ============================================
echo.

REM Step 1: 定位 Python（项目内旧目录 → 外部运行目录）
set "PYTHON_EXE=%~dp0python\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%RT%\python\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [INFO] 未检测到 Python 运行时，转交环境安装脚本...
    call "%~dp0setup_env.bat"
    exit /b %errorlevel%
)
echo [1/2] Python ready: %PYTHON_EXE%

REM Step 2: 检查源码目录
if not exist "%~dp0src" (
    echo [ERROR] Missing directory: src
    pause
    exit /b 1
)

echo [2/2] Starting application...
echo       First launch may be slow (loading OCR models)...
echo.

"%PYTHON_EXE%" -B "%~dp0run.py"
set "EXIT_CODE=%errorlevel%"

echo.
if %EXIT_CODE% equ 0 (
    echo [Application exited normally]
) else (
    echo [Application exited with code: %EXIT_CODE%]
    echo.
    echo Tips:
    echo   1. 依赖缺失 - 打开应用后进入「设置 → 环境与模型」一键安装
    echo   2. OCR 模型缺失 - 同上，使用国内镜像安装
)
echo.
pause >nul
exit /b %EXIT_CODE%
