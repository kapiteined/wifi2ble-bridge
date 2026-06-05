#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_DIR="$ROOT_DIR/python"
VENV_DIR="$PY_DIR/.venv"
REQUIREMENTS_FILE="$PY_DIR/requirements.txt"
APP_FILE="$PY_DIR/ble_scan.py"

if [[ ! -f "$APP_FILE" ]]; then
  echo "[error] Scanner script not found: $APP_FILE" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[error] python3 is not installed" >&2
  exit 1
fi

if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
  if [[ -d "$VENV_DIR" ]]; then
    echo "[warn] Incomplete virtual environment found in $VENV_DIR, recreating"
    rm -rf "$VENV_DIR"
  fi
  echo "[info] Creating virtual environment in $VENV_DIR"
  if ! python3 -m venv "$VENV_DIR"; then
    echo "[error] Failed to create virtual environment." >&2
    echo "       Install python3-venv (or python3.11-venv) and retry." >&2
    exit 1
  fi
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip >/dev/null
python -m pip install -r "$REQUIREMENTS_FILE"

echo "[info] Starting BLE scan"
exec python "$APP_FILE" "$@"
