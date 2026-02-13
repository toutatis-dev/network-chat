@echo off
setlocal

:: Get the directory of this script
SET "BASE_DIR=%~dp0"
SET "VENV_DIR=%BASE_DIR%venv"
SET "REQ_FILE=%BASE_DIR%requirements.txt"
SET "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

:: 1. Check if Python is installed globally
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 GOTO ERROR_NO_PYTHON

:: 2. Check if Venv exists
IF NOT EXIST "%VENV_DIR%" GOTO CREATE_VENV

:: 3. Check if Venv is valid (executable works)
"%PYTHON_EXE%" --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 GOTO RECREATE_VENV

:: 4. Check if dependencies are installed and package imports resolve
"%PYTHON_EXE%" -c "import prompt_toolkit, portalocker, watchdog, huddle_chat.ui" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 GOTO INSTALL_DEPS

:: If all good, run
GOTO RUN_APP

:RECREATE_VENV
echo [System] Detected broken virtual environment. Recreating...
rmdir /s /q "%VENV_DIR%"

:CREATE_VENV
echo [System] Creating virtual environment...
python -m venv "%VENV_DIR%"
IF %ERRORLEVEL% NEQ 0 GOTO ERROR_VENV_CREATE

:INSTALL_DEPS
echo [System] Installing/Updating dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pip >nul 2>&1
"%PYTHON_EXE%" -m pip install -r "%REQ_FILE%"
IF %ERRORLEVEL% NEQ 0 GOTO ERROR_INSTALL

:RUN_APP
echo [System] Starting Huddle Chat...
"%PYTHON_EXE%" "%BASE_DIR%chat.py"
GOTO END

:ERROR_NO_PYTHON
echo [Error] Python is not found in your PATH.
echo Please install Python from https://www.python.org/downloads/
pause
exit /b 1

:ERROR_VENV_CREATE
echo [Error] Failed to create virtual environment.
pause
exit /b 1

:ERROR_INSTALL
echo [Error] Failed to install dependencies.
pause
exit /b 1

:END
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [System] Application exited with error code %ERRORLEVEL%.
    pause
)
