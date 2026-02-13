#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status.

TARGETS="chat.py tests/*.py"

echo "--- 1. Formatting (Black) ---"
venv/bin/black $TARGETS

echo -e "
--- 2. Linting (Flake8) ---"
venv/bin/flake8 $TARGETS --ignore=E501

echo -e "
--- 3. Type Checking (Mypy) ---"
venv/bin/mypy chat.py

echo -e "
--- 4. Testing (Pytest) ---"
venv/bin/pytest

echo -e "
✅ All Checks Passed!"
