#!/usr/bin/env bash
set -euo pipefail

PREFIX="/usr/local"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix)
      shift
      PREFIX="${1:-}"
      if [[ -z "$PREFIX" ]]; then
        echo "[error] --prefix requires a value" >&2
        exit 2
      fi
      ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--prefix DIR]

Install wifi2ble-bridge Python relay tooling into a system prefix.

Defaults:
  --prefix /usr/local

Installed files:
  BIN: \
    $PREFIX/bin/wifi2ble-bridge-relay\
    $PREFIX/bin/wifi2ble-bridge-scan
  LIB: \
    $PREFIX/lib/wifi2ble-bridge/python/*
  SYSTEMD: \
    /etc/systemd/system/wifi2ble-bridge-relay.service
  ENV (only if not already present): \
    /etc/default/wifi2ble-bridge-relay
EOF
      exit 0
      ;;
    *)
      echo "[error] Unknown argument: $1" >&2
      exit 2
      ;;
  esac
  shift
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_PY_DIR="$ROOT_DIR/python"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[error] This script must be run as root (use sudo)." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[error] python3 is not installed" >&2
  exit 1
fi

if ! python3 -c 'import venv' >/dev/null 2>&1; then
  echo "[error] Python venv module is not available." >&2
  echo "       Install python3-venv (or python3.11-venv) and retry." >&2
  exit 1
fi

if [[ ! -d "$SRC_PY_DIR" ]]; then
  echo "[error] Source python directory not found: $SRC_PY_DIR" >&2
  exit 1
fi

BIN_DIR="$PREFIX/bin"
LIB_DIR="$PREFIX/lib/wifi2ble-bridge"
DEST_PY_DIR="$LIB_DIR/python"

echo "[info] Installing to prefix: $PREFIX"
echo "[info] Creating directories"
install -d "$BIN_DIR" "$DEST_PY_DIR"

echo "[info] Installing Python files"
install -m 0644 "$SRC_PY_DIR/requirements.txt" "$DEST_PY_DIR/requirements.txt"
install -m 0755 "$SRC_PY_DIR/wifi2ble_bridge_scan.py" "$DEST_PY_DIR/wifi2ble_bridge_scan.py"
install -m 0755 "$SRC_PY_DIR/wifi2ble_bridge_relay.py" "$DEST_PY_DIR/wifi2ble_bridge_relay.py"

TMP_SCAN="$(mktemp)"
TMP_RELAY="$(mktemp)"
trap 'rm -f "$TMP_SCAN" "$TMP_RELAY"' EXIT

cat > "$TMP_SCAN" <<EOF
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$LIB_DIR"
VENV_DIR="\$APP_DIR/.venv"
REQ_FILE="\$APP_DIR/python/requirements.txt"
SCRIPT_FILE="\$APP_DIR/python/wifi2ble_bridge_scan.py"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[error] python3 is not installed" >&2
  exit 1
fi

if [[ ! -f "\$VENV_DIR/bin/activate" ]]; then
  if [[ -d "\$VENV_DIR" ]]; then
    echo "[warn] Incomplete virtual environment found in \$VENV_DIR, recreating"
    rm -rf "\$VENV_DIR"
  fi
  echo "[info] Creating virtual environment in \$VENV_DIR"
  if ! python3 -m venv "\$VENV_DIR"; then
    echo "[error] Failed to create virtual environment." >&2
    echo "       Install python3-venv (or python3.11-venv) and retry." >&2
    exit 1
  fi
fi

# shellcheck disable=SC1091
source "\$VENV_DIR/bin/activate"
python -m pip install --upgrade pip >/dev/null
python -m pip install -r "\$REQ_FILE"

exec python "\$SCRIPT_FILE" "\$@"
EOF

cat > "$TMP_RELAY" <<EOF
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$LIB_DIR"
VENV_DIR="\$APP_DIR/.venv"
REQ_FILE="\$APP_DIR/python/requirements.txt"
SCRIPT_FILE="\$APP_DIR/python/wifi2ble_bridge_relay.py"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[error] python3 is not installed" >&2
  exit 1
fi

if [[ ! -f "\$VENV_DIR/bin/activate" ]]; then
  if [[ -d "\$VENV_DIR" ]]; then
    echo "[warn] Incomplete virtual environment found in \$VENV_DIR, recreating"
    rm -rf "\$VENV_DIR"
  fi
  echo "[info] Creating virtual environment in \$VENV_DIR"
  if ! python3 -m venv "\$VENV_DIR"; then
    echo "[error] Failed to create virtual environment." >&2
    echo "       Install python3-venv (or python3.11-venv) and retry." >&2
    exit 1
  fi
fi

# shellcheck disable=SC1091
source "\$VENV_DIR/bin/activate"
python -m pip install --upgrade pip >/dev/null
python -m pip install -r "\$REQ_FILE"

HAS_BLE_ARG=0
for arg in "\$@"; do
  if [[ "\$arg" == --ble-address=* || "\$arg" == "--ble-address" ]]; then
    HAS_BLE_ARG=1
    break
  fi
done

if [[ "\$HAS_BLE_ARG" -eq 0 ]]; then
  if [[ -z "\${BLE_ADDRESS:-}" ]]; then
    echo "[error] Missing BLE address." >&2
    echo "       Set BLE_ADDRESS env var, or pass --ble-address AA:BB:CC:DD:EE:FF" >&2
    exit 2
  fi
  set -- --ble-address "\$BLE_ADDRESS" "\$@"
fi

exec python "\$SCRIPT_FILE" "\$@"
EOF

echo "[info] Installing launchers"
install -m 0755 "$TMP_SCAN" "$BIN_DIR/wifi2ble-bridge-scan"
install -m 0755 "$TMP_RELAY" "$BIN_DIR/wifi2ble-bridge-relay"

SYSTEMD_DIR="/etc/systemd/system"
SRC_SYSTEMD_DIR="$ROOT_DIR/systemd"
ENV_FILE="/etc/default/wifi2ble-bridge-relay"

if [[ -d "$SYSTEMD_DIR" && -f "$SRC_SYSTEMD_DIR/wifi2ble-bridge-relay.service" ]]; then
  echo "[info] Installing systemd unit"
  install -m 0644 "$SRC_SYSTEMD_DIR/wifi2ble-bridge-relay.service" "$SYSTEMD_DIR/wifi2ble-bridge-relay.service"

  if [[ ! -f "$ENV_FILE" ]]; then
    echo "[info] Installing environment file: $ENV_FILE"
    install -m 0640 "$SRC_SYSTEMD_DIR/wifi2ble-bridge-relay.env" "$ENV_FILE"
    echo "[warn] Set BLE_ADDRESS in $ENV_FILE before starting the service"
  else
    echo "[info] Environment file already exists, not overwriting: $ENV_FILE"
  fi

  systemctl daemon-reload 2>/dev/null || true
  echo "[ok] systemd unit installed"
  echo "[ok] Enable and start with:"
  echo "      sudo systemctl enable --now wifi2ble-bridge-relay.service"
else
  echo "[info] Skipping systemd installation (not a systemd system or unit source not found)"
fi

echo "[ok] Installed"
echo "[ok] Commands:"
echo "      $BIN_DIR/wifi2ble-bridge-scan"
echo "      $BIN_DIR/wifi2ble-bridge-relay"
