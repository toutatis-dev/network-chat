@echo off
set TARGETS=chat.py huddle_chat tests
set PYTHON=venv\Scripts\python.exe
echo --- 1. Formatting (Black) ---
%PYTHON% -m black %TARGETS%
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
set PYTEST_TMP=%CD%\.tmp\pytest
if not exist "%CD%\.tmp" mkdir "%CD%\.tmp"
set TMP=%PYTEST_TMP%
set TEMP=%PYTEST_TMP%
%PYTHON% -m pytest tests --basetemp "%PYTEST_TMP%"
IF %ERRORLEVEL% NEQ 0 (
    echo [Error] Tests failed.
    exit /b 1
)

echo.
echo [Success] All Checks Passed!
pause
