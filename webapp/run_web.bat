@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 优先使用项目根目录的 venv
set PY=python
if exist "..\venv\Scripts\python.exe" set PY=..\venv\Scripts\python.exe

echo 检查依赖...
%PY% -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo 依赖安装失败
    pause
    exit /b 1
)

echo.
echo 启动 ReportChecker Web 版 ...
echo 电脑访问: http://127.0.0.1:8000
echo 手机访问: http://本机局域网IP:8000  ^(与电脑同一 WiFi^)
echo.
%PY% -m uvicorn server:app --host 0.0.0.0 --port 8000
pause
