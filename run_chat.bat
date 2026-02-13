@echo off
setlocal

:: Get the directory of this script
SET "BASE_DIR=%~dp0"
IF "%BASE_DIR:~-1%"=="\" SET "BASE_DIR=%BASE_DIR:~0,-1%"
SET "PY_CMD="

:: 1. Resolve a global Python command (prefer py launcher on Windows)
py -3 --version >nul 2>&1
IF %ERRORLEVEL% EQU 0 SET "PY_CMD=py -3"

IF NOT DEFINED PY_CMD (
    python --version >nul 2>&1
    IF %ERRORLEVEL% EQU 0 SET "PY_CMD=python"
)

IF NOT DEFINED PY_CMD (
    python3 --version >nul 2>&1
    IF %ERRORLEVEL% EQU 0 SET "PY_CMD=python3"
)

IF NOT DEFINED PY_CMD GOTO ERROR_NO_PYTHON

cd /d "%BASE_DIR%"
%PY_CMD% -m huddle_chat.bootstrap --base-dir "%BASE_DIR%" --requirements requirements.txt %*
GOTO END

:ERROR_NO_PYTHON
echo [Error] Python is not found in your PATH.
echo Detected commands checked: py -3, python, python3
echo If Python is installed, enable the py launcher or add python.exe to PATH.
echo Download: https://www.python.org/downloads/
pause
exit /b 1

:END
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [System] Application exited with error code %ERRORLEVEL%.
    pause
)
