#!/usr/bin/env python3
"""Simple BLE handshake debugger for MeshCore companion."""

import asyncio
import sys
from bleak import BleakClient, BleakScanner

MESHCORE_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
MESHCORE_RX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
MESHCORE_TX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

CMD_APP_START = 0x01
CMD_DEVICE_QUERY = 0x16
PACKET_SELF_INFO = 0x05
PACKET_DEVICE_INFO = 0x0D


async def main(ble_address: str) -> None:
    print(f"[*] Resolving {ble_address} via BLE scan...")

    devices = await BleakScanner.discover(timeout=6.0, return_adv=True)
    target = None
    for device, _ in devices.values():
        if device.address.upper() == ble_address.upper():
            target = device
            break

    if target is None:
        print(f"[-] Device not found in scan: {ble_address}")
        sys.exit(1)

    print(f"[*] Connecting to {target.address} ({target.name or 'unknown'})...")
    
    try:
        async with BleakClient(
            target,
            timeout=15.0,
            disconnected_callback=None
        ) as client:
            print("[+] Connected!")
            
            # Check services
            print("[*] Checking services...")
            services = client.services
            print(f"[+] Found {len(services.services)} services")
            
            # Check our service
            service = services.get_service(MESHCORE_SERVICE_UUID)
            if not service:
                print(f"[-] Service {MESHCORE_SERVICE_UUID} not found!")
                return
            
            print(f"[+] Found MeshCore service")
            
            # Check RX/TX characteristics
            rx_char = service.get_characteristic(MESHCORE_RX_UUID)
            tx_char = service.get_characteristic(MESHCORE_TX_UUID)
            
            if not rx_char:
                print(f"[-] RX characteristic not found!")
                return
            if not tx_char:
                print(f"[-] TX characteristic not found!")
                return
            
            print("[+] Found RX and TX characteristics")
            
            # Setup notification queue
            notify_queue: asyncio.Queue[bytes] = asyncio.Queue()
            
            def on_notify(_: int, data: bytearray) -> None:
                print(f"[<] RX: {bytes(data).hex()}")
                notify_queue.put_nowait(bytes(data))
            
            await client.start_notify(MESHCORE_TX_UUID, on_notify)
            print("[+] Notifications enabled on TX characteristic")
            
            # Send APP_START
            print("[*] Sending CMD_APP_START...")
            app_start = bytes([CMD_APP_START, 0, 0, 0, 0, 0, 0, 0]) + b"mesh-emu-debug"
            await client.write_gatt_char(MESHCORE_RX_UUID, app_start, response=True)
            print(f"[>] TX: {app_start.hex()}")
            
            # Wait for SELF_INFO
            print("[*] Waiting for SELF_INFO (timeout 8s)...")
            try:
                for _ in range(80):  # 80 * 100ms = 8s
                    try:
                        packet = await asyncio.wait_for(notify_queue.get(), timeout=0.1)
                        if packet[0] == PACKET_SELF_INFO:
                            print(f"[+] SELF_INFO received: {packet.hex()}")
                            print(f"    Length: {len(packet)}")
                            print(f"    Type: 0x{packet[0]:02X}")
                            break
                    except asyncio.TimeoutError:
                        pass
                else:
                    print("[-] SELF_INFO timeout!")
                    return
            except Exception as e:
                print(f"[-] Error waiting for SELF_INFO: {e}")
                return
            
            # Send DEVICE_QUERY
            print("[*] Sending CMD_DEVICE_QUERY...")
            dev_query = bytes([CMD_DEVICE_QUERY, 0x03])
            await client.write_gatt_char(MESHCORE_RX_UUID, dev_query, response=True)
            print(f"[>] TX: {dev_query.hex()}")
            
            # Wait for DEVICE_INFO
            print("[*] Waiting for DEVICE_INFO (timeout 5s)...")
            try:
                for _ in range(50):  # 50 * 100ms = 5s
                    try:
                        packet = await asyncio.wait_for(notify_queue.get(), timeout=0.1)
                        if packet[0] == PACKET_DEVICE_INFO:
                            print(f"[+] DEVICE_INFO received: {packet.hex()}")
                            print(f"    Length: {len(packet)}")
                            print(f"    Type: 0x{packet[0]:02X}")
                            break
                    except asyncio.TimeoutError:
                        pass
                else:
                    print("[!] DEVICE_INFO timeout (optional)")
            except Exception as e:
                print(f"[!] Error waiting for DEVICE_INFO: {e}")
            
            await client.stop_notify(MESHCORE_TX_UUID)
            print("[+] Done!")
            
    except Exception as e:
        print(f"[-] Connection failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: debug_ble_handshake.py <BLE_ADDRESS>")
        sys.exit(1)
    
    asyncio.run(main(sys.argv[1]))
