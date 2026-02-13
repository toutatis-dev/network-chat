#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_CMD=""

resolve_python() {
  if command -v python3 >/dev/null 2>&1; then
    PY_CMD="python3"
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    PY_CMD="python"
    return 0
  fi
  return 1
}

if ! resolve_python; then
  echo "[Error] Python is not found in your PATH."
  echo "Detected commands checked: python3, python"
  echo "Please install Python 3 and add it to PATH."
  exit 1
fi

cd "$BASE_DIR"
"$PY_CMD" -m huddle_chat.bootstrap --base-dir "$BASE_DIR" --requirements requirements.txt "$@"
