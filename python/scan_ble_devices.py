#!/usr/bin/env python3
"""Scan nearby BLE devices and print useful addresses for relay setup."""

from __future__ import annotations

import argparse
import asyncio

from bleak import BleakScanner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan nearby BLE devices")
    parser.add_argument("--timeout", type=float, default=8.0, help="Scan duration in seconds (default: 8)")
    parser.add_argument("--filter", default="", help="Only show devices whose name/address contains this text")
    return parser.parse_args()


def _matches_filter(address: str, name: str, needle: str) -> bool:
    if not needle:
        return True
    needle_l = needle.lower()
    return needle_l in address.lower() or needle_l in name.lower()


async def main() -> int:
    args = parse_args()

    print(f"[info] Scanning BLE devices for {args.timeout:.1f}s...")
    devices = await BleakScanner.discover(timeout=args.timeout, return_adv=True)

    rows = []
    for _, (device, adv) in devices.items():
        address = device.address or "(unknown)"
        name = device.name or "(no name)"
        if _matches_filter(address, name, args.filter):
            rows.append((address, name, adv.rssi))

    rows.sort(key=lambda x: (x[2] if x[2] is not None else -9999), reverse=True)

    if not rows:
        print("[warn] No matching BLE devices found.")
        print("[hint] Check if the companion is powered on, advertising, and nearby.")
        return 1

    print()
    print("Address              RSSI   Name")
    print("-------------------  -----  ------------------------------")
    for address, name, rssi in rows:
        rssi_text = str(rssi) if rssi is not None else "n/a"
        print(f"{address:<19}  {rssi_text:>5}  {name}")

    print()
    print("[hint] Gebruik het MAC-adres in:")
    print("       ./start.sh --ble-address AA:BB:CC:DD:EE:FF")
    print("[hint] MeshCore devices hebben vaak een naam met 'MeshCore'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
