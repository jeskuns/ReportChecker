@echo off
chcp 65001 >nul
title ReportChecker
color 0A

cd /d "%~dp0"

echo.
echo ============================================
echo     ReportChecker - Test Report Validator
echo ============================================
echo.

REM Step 1: Check embedded Python
echo [1/3] Checking environment...
set "PYTHON_EXE=%~dp0python\python.exe"
if not exist "%PYTHON_EXE%" (
    echo.
    echo [ERROR] Python not found: %PYTHON_EXE%
    echo Please make sure the python folder is in the same directory.
    echo.
    pause
    exit /b 1
)
echo       OK Python ready

REM Step 2: pywin32 first-time registration
echo [2/3] Checking system components...
set "PYWIN32_POSTINSTALL=%~dp0python\Scripts\pywin32_postinstall.exe"
if exist "%PYWIN32_POSTINSTALL%" (
    if not exist "%windir%\system32\pythoncom311.dll" (
        echo       First run detected, registering pywin32 COM...
        "%PYWIN32_POSTINSTALL%" -install >nul 2>&1
        if %errorlevel% equ 0 (
            echo       OK pywin32 registered
        ) else (
            echo       [WARN] pywin32 registration may have failed
            echo       Try running this script as Administrator
        )
    ) else (
        echo       OK system components ready
    )
)

REM Step 3: Check required directories
set "MISSING_DIRS="
if not exist "%~dp0src"            set "MISSING_DIRS=%MISSING_DIRS% src"
if not exist "%~dp0templates"      set "MISSING_DIRS=%MISSING_DIRS% templates"
if not exist "%~dp0deps\tesseract" set "MISSING_DIRS=%MISSING_DIRS% deps\tesseract"
if not exist "%~dp0models"         set "MISSING_DIRS=%MISSING_DIRS% models"

if defined MISSING_DIRS (
    echo.
    echo [ERROR] Missing directories:%MISSING_DIRS%
    echo Please verify project files are complete.
    echo.
    pause
    exit /b 1
)
echo       OK project structure complete

REM Step 4: Launch GUI
echo.
echo [3/3] Starting application...
echo       First launch may be slow (loading OCR models)...
echo.
echo ----------------------------------------------
echo.

"%PYTHON_EXE%" -B "%~dp0run.py"
set "EXIT_CODE=%errorlevel%"

echo.
echo ----------------------------------------------
if %EXIT_CODE% equ 0 (
    echo [Application exited normally]
) else (
    echo [Application exited with code: %EXIT_CODE%]
    echo.
    echo Troubleshooting:
    echo   1. DLL missing - check deps directory
    echo   2. OCR load failed - check models\ocr
    echo   3. Encoding issues - run chcp 65001
)
echo.
echo Press any key to close...
pause >nul
exit /b %EXIT_CODE%
