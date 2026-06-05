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

Install mesh-emu Python relay tooling into a system prefix.

Defaults:
  --prefix /usr/local

Installed files:
  BIN: \
    $PREFIX/bin/mesh-emu-relay\
    $PREFIX/bin/mesh-emu-scan
  LIB: \
    $PREFIX/lib/mesh-emu/python/*
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

if [[ ! -d "$SRC_PY_DIR" ]]; then
  echo "[error] Source python directory not found: $SRC_PY_DIR" >&2
  exit 1
fi

BIN_DIR="$PREFIX/bin"
LIB_DIR="$PREFIX/lib/mesh-emu"
DEST_PY_DIR="$LIB_DIR/python"

echo "[info] Installing to prefix: $PREFIX"
echo "[info] Creating directories"
install -d "$BIN_DIR" "$DEST_PY_DIR"

echo "[info] Installing Python files"
install -m 0644 "$SRC_PY_DIR/requirements.txt" "$DEST_PY_DIR/requirements.txt"
install -m 0755 "$SRC_PY_DIR/ble_scan.py" "$DEST_PY_DIR/ble_scan.py"
install -m 0755 "$SRC_PY_DIR/meshcore_tcp_ble_relay.py" "$DEST_PY_DIR/meshcore_tcp_ble_relay.py"

TMP_SCAN="$(mktemp)"
TMP_RELAY="$(mktemp)"
trap 'rm -f "$TMP_SCAN" "$TMP_RELAY"' EXIT

cat > "$TMP_SCAN" <<EOF
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$LIB_DIR"
VENV_DIR="\$APP_DIR/.venv"
REQ_FILE="\$APP_DIR/python/requirements.txt"
SCRIPT_FILE="\$APP_DIR/python/ble_scan.py"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[error] python3 is not installed" >&2
  exit 1
fi

if [[ ! -d "\$VENV_DIR" ]]; then
  echo "[info] Creating virtual environment in \$VENV_DIR"
  python3 -m venv "\$VENV_DIR"
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
SCRIPT_FILE="\$APP_DIR/python/meshcore_tcp_ble_relay.py"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[error] python3 is not installed" >&2
  exit 1
fi

if [[ ! -d "\$VENV_DIR" ]]; then
  echo "[info] Creating virtual environment in \$VENV_DIR"
  python3 -m venv "\$VENV_DIR"
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
install -m 0755 "$TMP_SCAN" "$BIN_DIR/mesh-emu-scan"
install -m 0755 "$TMP_RELAY" "$BIN_DIR/mesh-emu-relay"

echo "[ok] Installed"
echo "[ok] Commands:"
echo "      $BIN_DIR/mesh-emu-scan"
echo "      $BIN_DIR/mesh-emu-relay"
