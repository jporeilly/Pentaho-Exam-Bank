@echo off
title Question Bank Generator
cd /d "%~dp0"

:: Load environment variables from .env file
if exist ".env" (
    for /f "usebackq tokens=* eol=#" %%a in (".env") do (
        set "%%a"
    )
)

set "PORT_FILE=%TEMP%\question_bank_port.txt"

:: If a previous instance is running, kill it using the saved port
if exist "%PORT_FILE%" call :kill_port_from_file
:: Also try the default port
call :kill_port 7777

:: Check if virtual environment is healthy (activate.bat must exist)
if not exist "venv\Scripts\activate.bat" (
    echo Virtual environment is missing or corrupted.
    call :repair_venv
    if not exist "venv\Scripts\activate.bat" (
        echo ERROR: Could not repair virtual environment.
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

:: Check key dependencies are actually installed
python -c "import nicegui" >nul 2>&1
if errorlevel 1 (
    echo Dependencies are missing — repairing virtual environment...
    call :repair_venv
    if not exist "venv\Scripts\activate.bat" (
        echo ERROR: Could not repair virtual environment.
        pause
        exit /b 1
    )
    call venv\Scripts\activate.bat
)

:: Launch the app
echo Starting Question Bank Generator...
python main.py

:: Kill any leftover process on the actual port used
if exist "%PORT_FILE%" call :cleanup_port_file

exit

:repair_venv
:: Auto-repair: rebuild venv from requirements.txt
echo.
echo ============================================================
echo   Auto-repairing virtual environment...
echo ============================================================
echo.
:: Save current package list if pip is still functional
if exist "venv\Scripts\pip.exe" (
    echo Saving installed package list...
    venv\Scripts\pip.exe freeze > "assets\db\packages_backup.txt" 2>nul
    if not errorlevel 1 (
        echo Saved to assets\db\packages_backup.txt
    )
)
:: Remove broken venv
if exist "venv" (
    echo Removing corrupted venv...
    rmdir /s /q venv
)
:: Recreate
echo Creating fresh virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    echo Make sure Python 3.10+ is installed and in PATH.
    goto :eof
)
call venv\Scripts\activate.bat
echo Installing dependencies from requirements.txt...
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    goto :eof
)
echo.
echo Virtual environment repaired successfully.
echo.
goto :eof

:kill_port_from_file
:: Read port from file and kill that port (outside if-block to avoid expansion issues)
set /p PREV_PORT=<"%PORT_FILE%"
call :kill_port %PREV_PORT%
goto :eof

:cleanup_port_file
:: Read port from file, kill it, delete the file
set /p USED_PORT=<"%PORT_FILE%"
call :kill_port %USED_PORT%
del "%PORT_FILE%" >nul 2>&1
goto :eof

:kill_port
:: Usage: call :kill_port <port_number>
if "%~1"=="" goto :eof
netstat -ano | findstr ":%~1 " >nul 2>&1
if not errorlevel 1 (
    echo Releasing port %~1...
    for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%~1 "') do (
        taskkill /f /pid %%p >nul 2>&1
    )
    timeout /t 1 /nobreak >nul
)
goto :eof
