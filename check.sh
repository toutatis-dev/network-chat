#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status.

TARGETS="chat.py huddle_chat tests"
VENV_DIR="venv"
PYTHON_EXE="$VENV_DIR/bin/python"
PY_CMD=""

if command -v python3 >/dev/null 2>&1; then
  PY_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PY_CMD="python"
else
  echo "[Error] Python is not found in PATH. Checked: python3, python."
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "[System] Creating virtual environment..."
  "$PY_CMD" -m venv "$VENV_DIR"
fi

echo "[System] Installing/Updating dev dependencies..."
"$PYTHON_EXE" -m pip install --upgrade pip >/dev/null 2>&1
"$PYTHON_EXE" -m pip install -r requirements-dev.txt

echo "--- 1. Formatting (Black) ---"
"$PYTHON_EXE" -m black $TARGETS

echo -e "\n--- 2. Linting (Flake8) ---"
"$PYTHON_EXE" -m flake8 $TARGETS --ignore=E501,E203,W503 --jobs=1

echo -e "\n--- 3. Type Checking (Mypy) ---"
"$PYTHON_EXE" -m mypy chat.py huddle_chat

echo -e "\n--- 4. Testing (Pytest) ---"
PYTEST_TMP="$(pwd)/.tmp/pytest"
mkdir -p "$PYTEST_TMP"
TMPDIR="$PYTEST_TMP" "$PYTHON_EXE" -m pytest tests --basetemp "$PYTEST_TMP"

echo -e "\n[Success] All Checks Passed!"
