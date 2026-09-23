@echo off
title Pentaho Exam Bank - Installer
cd /d "%~dp0"

echo ============================================================
echo   Pentaho Exam Bank - Installer
echo ============================================================
echo.

:: Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Create virtual environment
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Activate and install
echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt
:: The dev set is separate so the installer does not vendor pytest.
if exist "requirements-dev.txt" pip install -r requirements-dev.txt

if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

:: Create data directories
if not exist "assets\db" mkdir "assets\db"
if not exist "assets\db\backups" mkdir "assets\db\backups"
if not exist "assets\pptx" mkdir "assets\pptx"
if not exist "assets\temp" mkdir "assets\temp"

echo.
echo ============================================================
echo   Installation complete!
echo.
echo   Data stored in: assets\db\
echo   PPTX cache in:  assets\pptx\
echo.
echo   Run 'run.bat' to start the application.
echo ============================================================
pause
