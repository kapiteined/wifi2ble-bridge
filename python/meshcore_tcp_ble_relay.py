#!/usr/bin/env python3
"""Compatibility wrapper for legacy script name.

Use wifi2ble_bridge_relay.py instead.
"""

from wifi2ble_bridge_relay import main


if __name__ == "__main__":
    raise SystemExit(main())
