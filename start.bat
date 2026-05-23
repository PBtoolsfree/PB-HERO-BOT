@echo off
title PB Hero Bot - Startup Wizard
echo ===================================================
echo PB HERO BOT - WEB DASHBOARD STARTUP WIZARD
echo ===================================================
echo.

:: Check python command
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=python
    goto found_python
)

:: Check py command
py --version >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=py
    goto found_python
)

echo [ERROR] Python was not found on your system!
echo Please make sure Python is installed and added to your system PATH.
echo.
pause
exit /b 1

:found_python
echo [INFO] Using Python command: %PY_CMD%
echo.

echo [INFO] Verifying and installing required packages...
%PY_CMD% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [WARNING] Failed to verify/install requirements.
    echo The dashboard might still run if packages are already installed.
    echo.
) else (
    echo [SUCCESS] Dependencies verified.
    echo.
)

echo [INFO] Starting Web Dashboard Server on http://127.0.0.1:8000 ...
echo.
%PY_CMD% web_dashboard.py
pause
