@echo off
:: Start the Pentaho Exam Bank.
::
:: One server now. The API serves the React front end from frontend\dist at
:: its own root, so there is a single port and a single window - the NiceGUI
:: layer that used to run alongside it on 7777 is gone.
::
:: The Content Editor's Questions button launches THIS FILE with PEB_COURSE
:: set, and does not know or care which port anything listens on. Keep the
:: name and keep loading .env, and that button keeps working.
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

set "API_PORT_FILE=%TEMP%\exam_bank_api_port.txt"
set "UI_PORT_FILE=%TEMP%\exam_bank_port.txt"

set "API_PORT=%PEB_API_PORT%"
:: QB_API_PORT is the name from when this was the Question Bank; still honoured.
if "%API_PORT%"=="" set "API_PORT=%QB_API_PORT%"
if "%API_PORT%"=="" set "API_PORT=7788"

:: Release ports a previous run left behind. The second file is the old
:: NiceGUI port: a machine that ran the previous version still has one
:: sitting in TEMP, and the process it names may still be holding 7777.
if exist "%API_PORT_FILE%" call :kill_port_from_file "%API_PORT_FILE%"
if exist "%UI_PORT_FILE%" call :cleanup_port_file "%UI_PORT_FILE%"
call :kill_port %API_PORT%

:: Verify the environment. _venv.bat checks fastapi when given no module.
:: %~dp0 is this script's own directory. Calling a sibling by bare name fails
:: outright where NoDefaultCurrentDirectoryInExePath=1 is set, which stops cmd
:: resolving an executable from the current directory.
call "%~dp0_venv.bat"
if errorlevel 1 (
    pause
    exit /b 1
)

:: The front end is served from a BUILD, not from Vite, so the build has to be
:: current. It is rebuilt every start rather than only when missing: a build
:: takes about five seconds, and "only if missing" means every git pull leaves
:: the old interface in place with nothing on screen saying so.
::
:: npm install is the slow one, so that runs only when node_modules is absent.
where npm >nul 2>&1
if errorlevel 1 goto :no_npm

cd /d "%~dp0frontend"
if not exist "node_modules" (
    echo Installing front-end dependencies - this happens once.
    call npm install
    if errorlevel 1 goto :no_build
)
echo Building the interface...
call npm run build
if errorlevel 1 goto :no_build
cd /d "%~dp0"

:check_build
:: Without a build the API answers on /api and the root is a 404, which reads
:: as "the app is broken" rather than "the interface was never built".
if not exist "%~dp0frontend\dist\index.html" goto :no_build

echo Starting the Exam Bank on port %API_PORT%...
"%VENV_PY%" -m exam_bank.api --port %API_PORT% --open

:: The server has exited - clean up after it.
call :kill_port %API_PORT%
if exist "%API_PORT_FILE%" call :cleanup_port_file "%API_PORT_FILE%"
exit /b 0

:no_npm
cd /d "%~dp0"
if exist "%~dp0frontend\dist\index.html" (
    echo Node.js was not found, so the interface was not rebuilt.
    echo Using the build that is already there.
    goto :check_build
)
goto :no_build

:no_build
cd /d "%~dp0"
echo.
echo ERROR: The interface could not be built.
echo.
echo   Node.js is required to build it. Install it from https://nodejs.org
echo   and run this file again, or build it by hand:
echo.
echo       cd frontend
echo       npm install
echo       npm run build
echo.
pause
exit /b 1

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
