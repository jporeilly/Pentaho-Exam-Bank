@echo off
:: Start the Exam Bank API on its own.
:: run.bat starts this alongside the UI; use this when you want only the API
:: - driving it from a REST client, or developing the React front end that
:: replaces the NiceGUI layer in 0.4.0.
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
