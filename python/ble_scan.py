#!/usr/bin/env python3
"""Scan for BLE devices and display their details."""

import asyncio
from bleak import BleakScanner

MESHCORE_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"


async def scan_devices():
    print("[info] Scanning for BLE devices (6 seconds)...")
    devices = await BleakScanner.discover(timeout=6.0, return_adv=True)
    
    meshcore_devices = []
    all_devices = []
    
    for device, adv_data in devices.values():
        is_meshcore = MESHCORE_SERVICE_UUID.lower() in [uuid.lower() for uuid in adv_data.service_uuids]
        device_info = {
            "name": device.name or "(unnamed)",
            "address": device.address,
            "tx_power": adv_data.tx_power,
            "is_meshcore": is_meshcore,
        }
        all_devices.append(device_info)
        if is_meshcore:
            meshcore_devices.append(device_info)
    
    print(f"\n[info] Found {len(all_devices)} BLE devices, {len(meshcore_devices)} MeshCore devices\n")
    
    if meshcore_devices:
        print("=== MeshCore Companion Devices ===")
        for dev in meshcore_devices:
            print(f"  {dev['name']:20s} | {dev['address']:18s} | TX Power: {dev['tx_power']}")
    
    if all_devices:
        print("\n=== All BLE Devices ===")
        for dev in all_devices:
            marker = "★ MeshCore" if dev["is_meshcore"] else ""
            print(f"  {dev['name']:20s} | {dev['address']:18s} {marker}")


if __name__ == "__main__":
    asyncio.run(scan_devices())
