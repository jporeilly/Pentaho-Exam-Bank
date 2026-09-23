@echo off
:: Shared venv check and auto-repair, called by run.bat and run-api.bat.
:: Kept in one file because it was going to be pasted into the second
:: launcher otherwise, and then only one of them would ever get fixed.
::
:: Usage:  call "%~dp0_venv.bat" <module-to-verify>
::   e.g.  call "%~dp0_venv.bat" nicegui
::
:: On success sets VENV_PY to the venv's python.exe. On failure sets
:: ERRORLEVEL 1 and prints why.
::
:: Two things this file is careful about, both learned the hard way:
::
:: 1. It sets VENV_PY to an EXPLICIT path and the callers use it, instead of
::    calling activate.bat and trusting `python` to mean the venv. On a
::    machine with the Windows Store Python installed, `python` can still
::    resolve to the Store build through its App Execution Alias after
::    activation - so the dependency check passes against the WRONG
::    interpreter and the app then dies on the first package that is only in
::    the venv. That is a confusing failure a long way from its cause.
::
:: 2. Siblings are called with %~dp0, never by bare name. Where
::    NoDefaultCurrentDirectoryInExePath=1 is set, cmd will not resolve an
::    executable from the current directory at all and a bare name fails
::    outright.
::
:: ASCII only - a .bat is read in the console codepage, and anything else
:: turns into mojibake in the window the user is reading.

set "VERIFY_MODULE=%~1"
if "%VERIFY_MODULE%"=="" set "VERIFY_MODULE=fastapi"
set "VENV_PY=%~dp0venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo Virtual environment is missing or corrupted.
    call :repair_venv
    if not exist "%VENV_PY%" (
        echo ERROR: Could not repair virtual environment.
        exit /b 1
    )
)

"%VENV_PY%" -c "import %VERIFY_MODULE%" >nul 2>&1
if errorlevel 1 (
    echo Dependencies are missing - repairing virtual environment...
    call :repair_venv
    if not exist "%VENV_PY%" (
        echo ERROR: Could not repair virtual environment.
        exit /b 1
    )
    "%VENV_PY%" -c "import %VERIFY_MODULE%" >nul 2>&1
    if errorlevel 1 (
        echo ERROR: %VERIFY_MODULE% is still not importable after repair.
        exit /b 1
    )
)

exit /b 0

:repair_venv
echo.
echo ============================================================
echo   Auto-repairing virtual environment...
echo ============================================================
echo.
if exist "%~dp0venv\Scripts\pip.exe" (
    echo Saving installed package list...
    "%~dp0venv\Scripts\pip.exe" freeze > "%~dp0assets\db\packages_backup.txt" 2>nul
    if not errorlevel 1 (
        echo Saved to assets\db\packages_backup.txt
    )
)
if exist "%~dp0venv" (
    echo Removing corrupted venv...
    rmdir /s /q "%~dp0venv"
)
echo Creating fresh virtual environment...
python -m venv "%~dp0venv"
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    echo Make sure Python 3.10+ is installed and in PATH.
    goto :eof
)
echo Installing dependencies from requirements.txt...
"%VENV_PY%" -m pip install --upgrade pip >nul 2>&1
"%VENV_PY%" -m pip install -r "%~dp0requirements.txt"
if exist "%~dp0requirements-dev.txt" "%VENV_PY%" -m pip install -r "%~dp0requirements-dev.txt"
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    goto :eof
)
echo.
echo Virtual environment repaired successfully.
echo.
goto :eof
