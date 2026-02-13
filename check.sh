#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status.

TARGETS="chat.py huddle_chat tests"

echo "--- 1. Formatting (Black) ---"
venv/bin/black $TARGETS

echo -e "
--- 2. Linting (Flake8) ---"
venv/bin/flake8 $TARGETS --ignore=E501,E203 --jobs=1

echo -e "
--- 3. Type Checking (Mypy) ---"
venv/bin/mypy chat.py huddle_chat

echo -e "
--- 4. Testing (Pytest) ---"
PYTEST_TMP="$(pwd)/.tmp/pytest"
mkdir -p "$PYTEST_TMP"
TMPDIR="$PYTEST_TMP" venv/bin/pytest tests --basetemp "$PYTEST_TMP"

echo -e "
✅ All Checks Passed!"
