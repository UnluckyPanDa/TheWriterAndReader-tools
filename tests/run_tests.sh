#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON:-python3}"

if "$PYTHON_BIN" -c "import pytest" >/dev/null 2>&1; then
  "$PYTHON_BIN" -m pytest tests
else
  "$PYTHON_BIN" -m unittest discover -s tests
fi
