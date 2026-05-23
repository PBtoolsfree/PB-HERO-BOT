@echo off
title PB Hero Bot - Manual Updater & Diagnostics
echo ===================================================
echo PB HERO BOT - TERMINAL UPDATE & DIAGNOSTIC SYSTEM
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
echo Please make sure Python is installed and in your PATH.
echo.
pause
exit /b 1

:found_python
echo [INFO] Using Python command: %PY_CMD%
echo [INFO] Executing manual system update & diagnostics...
echo.

%PY_CMD% "%~dp0update_and_check.py"
echo.
echo Process complete. Press any key to exit.
pause
