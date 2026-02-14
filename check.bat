@echo off
setlocal
set TARGETS=chat.py huddle_chat tests
set VENV_DIR=venv
set PYTHON=%VENV_DIR%\Scripts\python.exe
set PY_CMD=
set MODE=%1
set CHECK_ONLY=0

if /I "%MODE%"=="" set MODE=--check
if /I "%MODE%"=="--check" set CHECK_ONLY=1
if /I "%MODE%"=="check" set CHECK_ONLY=1
if /I "%MODE%"=="--fix" set CHECK_ONLY=0
if /I "%MODE%"=="fix" set CHECK_ONLY=0
if /I NOT "%MODE%"=="--check" if /I NOT "%MODE%"=="check" if /I NOT "%MODE%"=="--fix" if /I NOT "%MODE%"=="fix" (
    echo Usage: check.bat [--check^|--fix]
    exit /b 1
)

py -3 --version >nul 2>&1
IF %ERRORLEVEL% EQU 0 set "PY_CMD=py -3"

IF NOT DEFINED PY_CMD (
    python --version >nul 2>&1
    IF %ERRORLEVEL% EQU 0 set "PY_CMD=python"
)

IF NOT DEFINED PY_CMD (
    python3 --version >nul 2>&1
    IF %ERRORLEVEL% EQU 0 set "PY_CMD=python3"
)

IF NOT DEFINED PY_CMD (
    echo [Error] Python is not found in PATH. Checked: py -3, python, python3.
    exit /b 1
)

IF NOT EXIST "%VENV_DIR%" (
    echo [System] Creating virtual environment...
    %PY_CMD% -m venv "%VENV_DIR%"
    IF %ERRORLEVEL% NEQ 0 (
        echo [Error] Failed to create virtual environment.
        exit /b 1
    )
)

%PYTHON% -c "import black, flake8, mypy, pytest" >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [System] Installing/Updating dev dependencies...
    %PYTHON% -m pip install --upgrade pip >nul 2>&1
    %PYTHON% -m pip install -r requirements-dev.txt
    IF %ERRORLEVEL% NEQ 0 (
        echo [Error] Failed to install dependencies.
        exit /b 1
    )
)

if %CHECK_ONLY% EQU 1 (
    echo --- 1. Formatting Check (Black --check) ---
    %PYTHON% -m black --check %TARGETS%
) else (
    echo --- 1. Formatting (Black) ---
    %PYTHON% -m black %TARGETS%
)
IF %ERRORLEVEL% NEQ 0 (
    echo [Error] Formatting failed.
    exit /b 1
)

echo.
echo --- 2. Linting (Flake8) ---
%PYTHON% -m flake8 %TARGETS% --ignore=E501,E203,W503 --jobs=1
IF %ERRORLEVEL% NEQ 0 (
    echo [Error] Linting failed.
    exit /b 1
)

echo.
echo --- 3. Type Checking (Mypy) ---
%PYTHON% -m mypy chat.py huddle_chat
IF %ERRORLEVEL% NEQ 0 (
    echo [Error] Type checking failed.
    exit /b 1
)

echo.
echo --- 4. Testing (Pytest) ---
set TMP_ROOT=%CD%\.pytest_temp
set PYTEST_BASE=%TMP_ROOT%\basetemp
set PYTEST_WORK=%TMP_ROOT%\tmp
if exist "%TMP_ROOT%" rmdir /s /q "%TMP_ROOT%" >nul 2>&1
if not exist "%TMP_ROOT%" mkdir "%TMP_ROOT%"
if not exist "%PYTEST_BASE%" mkdir "%PYTEST_BASE%"
if not exist "%PYTEST_WORK%" mkdir "%PYTEST_WORK%"
set TMP=%PYTEST_WORK%
set TEMP=%PYTEST_WORK%
%PYTHON% -m pytest tests --basetemp "%PYTEST_BASE%"
IF %ERRORLEVEL% NEQ 0 (
    echo [Error] Tests failed.
    exit /b 1
)

echo.
echo [Success] All Checks Passed!
