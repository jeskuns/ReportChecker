@echo off
chcp 65001 >nul
title ReportChecker - 环境安装
color 0A

cd /d "%~dp0"

if "%REPORTCHECKER_HOME%"=="" (
    set "RT=%LOCALAPPDATA%\ReportChecker\runtime"
) else (
    set "RT=%REPORTCHECKER_HOME%"
)

if exist "%RT%\python\python.exe" goto :run

echo.
echo ============================================
echo   首次运行：安装 Python 运行时
echo   镜像：华为云 / npmmirror / 阿里云
echo ============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap_python.ps1" -RuntimeRoot "%RT%"
if errorlevel 1 (
    echo.
    echo [ERROR] Python 运行时安装失败，请检查网络后重试。
    pause
    exit /b 1
)

:run
"%RT%\python\python.exe" -B "%~dp0run.py"
set "EXIT_CODE=%errorlevel%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo [Application exited with code: %EXIT_CODE%]
    pause >nul
)
exit /b %EXIT_CODE%
