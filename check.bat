@echo off
echo --- 1. Formatting (Black) ---
venv\Scripts\black .
IF %ERRORLEVEL% NEQ 0 (
    echo [Error] Formatting failed.
    exit /b 1
)

echo.
echo --- 2. Linting (Flake8) ---
venv\Scripts\flake8 chat.py --ignore=E501
IF %ERRORLEVEL% NEQ 0 (
    echo [Error] Linting failed.
    exit /b 1
)

echo.
echo --- 3. Testing (Pytest) ---
venv\Scripts\pytest
IF %ERRORLEVEL% NEQ 0 (
    echo [Error] Tests failed.
    exit /b 1
)

echo.
echo [Success] All Checks Passed!
pause
