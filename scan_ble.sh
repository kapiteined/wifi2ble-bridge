#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_DIR="$ROOT_DIR/python"
VENV_DIR="$PY_DIR/.venv"
REQUIREMENTS_FILE="$PY_DIR/requirements.txt"
SCAN_FILE="$PY_DIR/scan_ble_devices.py"

if [[ ! -f "$SCAN_FILE" ]]; then
  echo "[error] Scanner script not found: $SCAN_FILE" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[error] python3 is not installed" >&2
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  echo "[info] Creating virtual environment in $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip >/dev/null
python -m pip install -r "$REQUIREMENTS_FILE"

echo "[info] Starting BLE scan"
exec python "$SCAN_FILE" "$@"
