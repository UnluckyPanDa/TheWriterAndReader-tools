#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TWR_DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/the-writer-and-reader"
RUNTIME_DIR="$TWR_DATA_DIR/runtime"
PYTHON_BIN="$RUNTIME_DIR/bin/python"
TWR_BIN="$RUNTIME_DIR/bin/twr"
MARKER="$TWR_DATA_DIR/initialized-0.1.5"
WHEEL="$SKILL_DIR/assets/the_writer_and_reader_tools-0.1.5-py3-none-any.whl"
EXPECTED_SHA256="723dda6a2e2b0e623b20e1bb6c4273401ca5934ada72498510bb8cb5532d8f69"

if [[ -f "$MARKER" && -x "$TWR_BIN" ]]; then
  printf '%s\n' "$TWR_BIN"
  exit 0
fi

mkdir -p "$TWR_DATA_DIR"
if command -v shasum >/dev/null 2>&1; then
  ACTUAL_SHA256="$(shasum -a 256 "$WHEEL" | awk '{print $1}')"
else
  ACTUAL_SHA256="$(sha256sum "$WHEEL" | awk '{print $1}')"
fi
if [[ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]]; then
  printf 'TWR wheel checksum mismatch.\n' >&2
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
    python3 -m venv "$RUNTIME_DIR"
  else
    if ! command -v uv >/dev/null 2>&1; then
      curl -LsSf https://astral.sh/uv/install.sh | sh
      export PATH="$HOME/.local/bin:$PATH"
    fi
    uv venv --python 3.11 "$RUNTIME_DIR"
  fi
fi

"$PYTHON_BIN" -m ensurepip --upgrade >/dev/null 2>&1 || true
"$PYTHON_BIN" -m pip install --upgrade "$WHEEL"

"$TWR_BIN" setup --ensure
touch "$MARKER"
printf '%s\n' "$TWR_BIN"
