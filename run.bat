@echo off
:: Start the Exam Bank: the API, and the NiceGUI interface on top of it.
::
:: Both are started because the app is mid-restack. The NiceGUI layer still
:: calls core directly and does not need the API, but the API is what the
:: React front end will use in 0.4.0, and having it up means it can be driven
:: and developed against while the old interface is still the one in use.
:: When the NiceGUI layer goes, this file stops starting it and nothing else
:: about the launch changes.
::
:: ASCII only - a .bat is read in the console codepage, and anything else
:: turns into mojibake in the window the user is reading.
title Pentaho Exam Bank
cd /d "%~dp0"

:: Load environment variables from .env
if exist ".env" (
    for /f "usebackq tokens=* eol=#" %%a in (".env") do (
        set "%%a"
    )
)

set "PORT_FILE=%TEMP%\exam_bank_port.txt"
set "API_PORT_FILE=%TEMP%\exam_bank_api_port.txt"

set "UI_PORT=7777"
set "API_PORT=%QB_API_PORT%"
if "%API_PORT%"=="" set "API_PORT=7788"

:: Release ports a previous run left behind
if exist "%PORT_FILE%" call :kill_port_from_file "%PORT_FILE%"
if exist "%API_PORT_FILE%" call :kill_port_from_file "%API_PORT_FILE%"
call :kill_port %UI_PORT%
call :kill_port %API_PORT%

:: Verify the environment once, for both servers.
:: %~dp0 is this script's own directory. Calling a sibling by bare name fails
:: outright where NoDefaultCurrentDirectoryInExePath=1 is set, which stops cmd
:: resolving an executable from the current directory.
call "%~dp0_venv.bat" nicegui
if errorlevel 1 (
    pause
    exit /b 1
)

:: The API goes to its own window so its log stays readable and closing it
:: does not take the interface down with it.
echo Starting the API on port %API_PORT%...
start "Pentaho Exam Bank - API" /min "%VENV_PY%" -m exam_bank.api --port %API_PORT%

echo Starting the interface on port %UI_PORT%...
"%VENV_PY%" main.py

:: The interface has exited - take the API down with it rather than leaving
:: an orphan holding the port until someone notices.
echo Stopping the API...
call :kill_port %API_PORT%
if exist "%PORT_FILE%" call :cleanup_port_file "%PORT_FILE%"
if exist "%API_PORT_FILE%" call :cleanup_port_file "%API_PORT_FILE%"

exit

:kill_port_from_file
set /p PREV_PORT=<%~1
call :kill_port %PREV_PORT%
goto :eof

:cleanup_port_file
set /p USED_PORT=<%~1
call :kill_port %USED_PORT%
del %~1 >nul 2>&1
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
