#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
if [[ -n "${PYTHON:-}" ]]; then
  PYTHON_BIN="$PYTHON"
elif [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="python3"
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
  echo "The test suite requires Python 3.11 or newer (found: $($PYTHON_BIN --version 2>&1))." >&2
  exit 2
fi

if "$PYTHON_BIN" -c "import pytest" >/dev/null 2>&1; then
  "$PYTHON_BIN" -m pytest tests
else
  "$PYTHON_BIN" -m unittest discover -s tests
fi

if command -v node >/dev/null 2>&1; then
  node --test tests/prompt-assets.test.mjs
fi
