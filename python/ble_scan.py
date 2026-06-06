#!/usr/bin/env python3
"""Compatibility wrapper for legacy script name.

Use wifi2ble_bridge_scan.py instead.
"""

import asyncio

from wifi2ble_bridge_scan import scan_devices


if __name__ == "__main__":
    asyncio.run(scan_devices())
