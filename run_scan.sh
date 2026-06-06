#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEW_SCRIPT="$ROOT_DIR/run_wifi2ble_bridge_scan.sh"

echo "[warn] Deprecated script name: run_scan.sh"
echo "[warn] Use: run_wifi2ble_bridge_scan.sh"
exec "$NEW_SCRIPT" "$@"
