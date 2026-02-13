@echo off
set TARGETS=chat.py tests\*.py
echo --- 1. Formatting (Black) ---
venv\Scripts\black %TARGETS%
IF %ERRORLEVEL% NEQ 0 (
    echo [Error] Formatting failed.
    exit /b 1
)

echo.
echo --- 2. Linting (Flake8) ---
venv\Scripts\flake8 %TARGETS% --ignore=E501
IF %ERRORLEVEL% NEQ 0 (
    echo [Error] Linting failed.
    exit /b 1
)

echo.
echo --- 3. Type Checking (Mypy) ---
venv\Scripts\mypy chat.py
IF %ERRORLEVEL% NEQ 0 (
    echo [Error] Type checking failed.
    exit /b 1
)

echo.
echo --- 4. Testing (Pytest) ---
venv\Scripts\pytest
IF %ERRORLEVEL% NEQ 0 (
    echo [Error] Tests failed.
    exit /b 1
)

echo.
echo [Success] All Checks Passed!
pause
