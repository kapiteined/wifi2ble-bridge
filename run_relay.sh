#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_DIR="$ROOT_DIR/python"
VENV_DIR="$PY_DIR/.venv"
REQUIREMENTS_FILE="$PY_DIR/requirements.txt"
APP_FILE="$PY_DIR/meshcore_tcp_ble_relay.py"

if [[ ! -f "$APP_FILE" ]]; then
  echo "[error] Relay script not found: $APP_FILE" >&2
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

HAS_BLE_ARG=0
for arg in "$@"; do
  if [[ "$arg" == --ble-address=* || "$arg" == "--ble-address" ]]; then
    HAS_BLE_ARG=1
    break
  fi
done

if [[ "$HAS_BLE_ARG" -eq 0 ]]; then
  if [[ -z "${BLE_ADDRESS:-}" ]]; then
    echo "[error] Missing BLE address." >&2
    echo "       Set BLE_ADDRESS env var, or pass --ble-address AA:BB:CC:DD:EE:FF" >&2
    exit 2
  fi
  set -- --ble-address "$BLE_ADDRESS" "$@"
fi

echo "[info] Starting MeshCore TCP->BLE relay"
exec python "$APP_FILE" "$@"
