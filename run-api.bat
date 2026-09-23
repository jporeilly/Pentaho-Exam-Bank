@echo off
:: Start the Exam Bank API on its own.
:: run.bat starts the same server WITH the built interface and opens a browser.
:: Use this one when you want the API alone - driving it from a REST client, or
:: running Vite against it while developing the front end.
:: ASCII only - a .bat is read in the console codepage.
title Pentaho Exam Bank - API
cd /d "%~dp0"

if exist ".env" (
    for /f "usebackq tokens=* eol=#" %%a in (".env") do (
        set "%%a"
    )
)

set "API_PORT=%QB_API_PORT%"
if "%API_PORT%"=="" set "API_PORT=7788"

:: %~dp0 is this script's own directory. Calling a sibling by bare name
:: fails outright where NoDefaultCurrentDirectoryInExePath=1 is set, which
:: stops cmd resolving an executable from the current directory - so the
:: path is always explicit rather than relying on the caller's cwd.
call "%~dp0_venv.bat" fastapi
if errorlevel 1 (
    pause
    exit /b 1
)

echo Starting the API on port %API_PORT%...
"%VENV_PY%" -m exam_bank.api --port %API_PORT% %*

exit /b %errorlevel%
