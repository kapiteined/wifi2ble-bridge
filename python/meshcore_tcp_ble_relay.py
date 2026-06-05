#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025-2026 Ed Kapitein
# Portions generated with AI assistance
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Single-Pi MeshCore companion relay.

Flow:
- Accept one TCP client (Android MeshCore client side)
- Connect to MeshCore companion over BLE GATT
- Forward TCP -> BLE RX characteristic
- Forward BLE TX notifications -> TCP

Requires Linux BlueZ + Python bleak.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from dataclasses import dataclass
from typing import Optional

from bleak import BleakClient

MESHCORE_RX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # app -> firmware
MESHCORE_TX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # firmware -> app
TCP_FRAME_APP_TO_DEVICE = 0x3C  # '<'
TCP_FRAME_DEVICE_TO_APP = 0x3E  # '>'

COMMAND_NAMES = {
    0x01: "AppStart",
    0x04: "GetContacts",
    0x05: "GetDeviceTime",
    0x06: "SetDeviceTime",
    0x0A: "SyncNextMessage",
    0x14: "GetBatteryVoltage",
    0x16: "DeviceQuery",
    0x1F: "GetChannel",
    0x20: "SetChannel",
    0x38: "GetStats",
}

RESPONSE_NAMES = {
    0x00: "Ok",
    0x01: "Err",
    0x02: "ContactsStart",
    0x04: "EndOfContacts",
    0x05: "SelfInfo",
    0x09: "CurrTime",
    0x0A: "NoMoreMessages",
    0x0C: "BatteryVoltage",
    0x0D: "DeviceInfo",
    0x12: "ChannelInfo",
    0x18: "Stats",
}


@dataclass
class RelayConfig:
    tcp_host: str
    tcp_port: int
    ble_address: str
    ble_rx_uuid: str
    ble_tx_uuid: str
    debug_io: bool


class MeshcoreTcpBleRelay:
    def __init__(self, config: RelayConfig) -> None:
        self.config = config
        self._server: Optional[asyncio.AbstractServer] = None
        self._shutdown_event = asyncio.Event()
        self._active_client_lock = asyncio.Lock()
        self._client_writers: set[asyncio.StreamWriter] = set()
        self._client_tasks: set[asyncio.Task[None]] = set()
        self._shutdown_lock = asyncio.Lock()

    def _debug(self, message: str) -> None:
        if not self.config.debug_io:
            return
        print(f"[debug] {message}")

    async def run(self) -> None:
        self._debug("Relay starting")

        self._server = await asyncio.start_server(
            self._handle_client,
            host=self.config.tcp_host,
            port=self.config.tcp_port,
        )

        sockets = self._server.sockets or []
        for sock in sockets:
            addr = sock.getsockname()
            print(f"[info] TCP listening on {addr}")

        async with self._server:
            await self._shutdown_event.wait()
        self._debug("Relay stopped")

    async def shutdown(self) -> None:
        async with self._shutdown_lock:
            if self._shutdown_event.is_set():
                return

            self._debug("Shutdown requested")
            self._shutdown_event.set()
            if self._server is not None:
                self._server.close()
                await self._server.wait_closed()

            # Cancel any still-running client tasks to break out of read/write awaits.
            client_tasks = [task for task in self._client_tasks if not task.done()]
            for task in client_tasks:
                task.cancel()
            if client_tasks:
                await asyncio.gather(*client_tasks, return_exceptions=True)

            # Force-close any remaining client sockets.
            client_writers = list(self._client_writers)
            for writer in client_writers:
                writer.close()
            for writer in client_writers:
                try:
                    await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
                except Exception:
                    pass

            self._debug("Shutdown complete")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")

        if self._active_client_lock.locked():
            print(f"[warn] Rejecting extra TCP client {peer}, only one active session is supported")
            writer.close()
            await writer.wait_closed()
            return

        async with self._active_client_lock:
            current_task = asyncio.current_task()
            if current_task is not None:
                self._client_tasks.add(current_task)
            self._client_writers.add(writer)
            self._debug(f"Starting client session for {peer}")
            print(f"[info] TCP client connected: {peer}")
            try:
                await self._run_client_session(reader, writer)
            except Exception as exc:  # broad by design for long-running relay
                print(f"[error] session failure: {exc}")
            finally:
                if current_task is not None:
                    self._client_tasks.discard(current_task)
                self._client_writers.discard(writer)
                writer.close()
                try:
                    await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
                except Exception:
                    pass
                print(f"[info] TCP client disconnected: {peer}")
                self._debug(f"Client session closed for {peer}")

    def _debug_log_io(self, direction: str, data: bytes) -> None:
        if not self.config.debug_io:
            return

        preview = data[:96].hex()
        if len(data) > 96:
            preview += "..."
        print(
            f"[debug] {direction} len={len(data)} hex={preview}",
            file=sys.stderr,
            flush=True,
        )

    def _describe_command(self, payload: bytes) -> str:
        if not payload:
            return "empty"
        command_code = payload[0]
        command_name = COMMAND_NAMES.get(command_code, f"0x{command_code:02x}")
        return f"cmd={command_name}({command_code:#04x}) payload_len={len(payload)}"

    def _describe_response(self, payload: bytes) -> str:
        if not payload:
            return "empty"
        response_code = payload[0]
        response_name = RESPONSE_NAMES.get(response_code, f"0x{response_code:02x}")
        return f"resp={response_name}({response_code:#04x}) payload_len={len(payload)}"

    def _debug_log_tcp_payload(self, payload: bytes) -> None:
        self._debug_log_io(f"TCP payload {self._describe_command(payload)}", payload)

    def _debug_log_ble_payload(self, payload: bytes) -> None:
        self._debug_log_io(f"BLE payload {self._describe_response(payload)}", payload)

    def _frame_tcp_payload(self, payload: bytes) -> bytes:
        if len(payload) > 0xFFFF:
            raise ValueError(f"payload too large for TCP frame: {len(payload)}")
        return bytes((TCP_FRAME_DEVICE_TO_APP, len(payload) & 0xFF, (len(payload) >> 8) & 0xFF)) + payload

    def _send_tcp_payload(self, writer: asyncio.StreamWriter, payload: bytes) -> None:
        framed_payload = self._frame_tcp_payload(payload)
        self._debug_log_io("TCP->", framed_payload)
        writer.write(framed_payload)

    def _decode_tcp_payloads(self, rx_buffer: bytearray, chunk: bytes) -> list[bytes]:
        rx_buffer.extend(chunk)
        payloads: list[bytes] = []

        while True:
            if len(rx_buffer) < 3:
                break

            if rx_buffer[0] not in (TCP_FRAME_APP_TO_DEVICE, TCP_FRAME_DEVICE_TO_APP):
                # Fallback for unexpected unframed streams.
                payloads.append(bytes(rx_buffer))
                rx_buffer.clear()
                break

            payload_len = rx_buffer[1] | (rx_buffer[2] << 8)
            frame_len = 3 + payload_len
            if len(rx_buffer) < frame_len:
                break

            payloads.append(bytes(rx_buffer[3:frame_len]))
            del rx_buffer[:frame_len]

        return payloads

    async def _run_client_session(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Bridge TCP client to BLE companion device."""
        if not self.config.ble_address:
            print("[error] BLE address not provided; set --ble-address")
            return

        print(f"[info] Connecting to BLE device: {self.config.ble_address}")
        try:
            def _on_ble_disconnected(_client: BleakClient) -> None:
                self._debug("BLE connection lost")

            async with BleakClient(self.config.ble_address, disconnected_callback=_on_ble_disconnected) as ble_client:
                print(f"[info] Connected to BLE companion")
                self._debug("BLE connection established")

                ble_rx_queue = asyncio.Queue()

                def on_ble_notification(sender, data):
                    """Non-async BLE callback; queue for async handler."""
                    if self._shutdown_event.is_set():
                        return
                    try:
                        ble_rx_queue.put_nowait(data)
                    except asyncio.QueueFull:
                        print("[warn] BLE RX queue full, dropping notification")

                await ble_client.start_notify(self.config.ble_tx_uuid, on_ble_notification)

                tcp_rx_buffer = bytearray()

                # Background task to relay BLE RX -> TCP
                async def ble_to_tcp_relay():
                    while not self._shutdown_event.is_set():
                        try:
                            ble_payload = await asyncio.wait_for(ble_rx_queue.get(), timeout=0.1)
                            self._debug_log_io("BLE->", ble_payload)
                            self._debug_log_ble_payload(ble_payload)
                            self._send_tcp_payload(writer, ble_payload)
                            await writer.drain()
                        except asyncio.TimeoutError:
                            pass
                        except Exception as e:
                            print(f"[error] BLE->TCP relay error: {e}")
                            break

                relay_task = asyncio.create_task(ble_to_tcp_relay())

                try:
                    while not self._shutdown_event.is_set():
                        chunk = await reader.read(512)
                        if not chunk:
                            self._debug("TCP read returned empty, client closed connection")
                            break

                        self._debug_log_io("TCP<-", chunk)
                        payloads = self._decode_tcp_payloads(tcp_rx_buffer, chunk)

                        for payload in payloads:
                            self._debug_log_io("TCP payload", payload)
                            self._debug_log_tcp_payload(payload)

                            if not payload:
                                continue

                            command_code = payload[0]
                            command_name = COMMAND_NAMES.get(command_code, f"0x{command_code:02x}")
                            self._debug(f"app command: {command_name} ({command_code:#04x})")

                            # Forward to BLE
                            self._debug_log_io("BLE<-", payload)
                            await ble_client.write_gatt_char(self.config.ble_rx_uuid, payload, response=False)
                            self._debug(f"Sent to BLE RX: {payload.hex()}")

                finally:
                    relay_task.cancel()
                    try:
                        await relay_task
                    except asyncio.CancelledError:
                        pass
                    await ble_client.stop_notify(self.config.ble_tx_uuid)
                    self._debug("BLE notifications stopped")

        except Exception as e:
            print(f"[error] BLE bridge error: {e}")
            if self.config.debug_io:
                import traceback
                traceback.print_exc()

def parse_args() -> RelayConfig:
    parser = argparse.ArgumentParser(description="MeshCore TCP to BLE GATT relay")
    parser.add_argument("--tcp-host", default="0.0.0.0", help="TCP bind host (default: 0.0.0.0)")
    parser.add_argument("--tcp-port", type=int, default=5000, help="TCP bind port (default: 5000)")
    parser.add_argument("--ble-address", default="", help="BLE MAC address of the companion (optional in probe mode)")
    parser.add_argument("--ble-rx-uuid", default=MESHCORE_RX_UUID, help="RX characteristic UUID (app -> device)")
    parser.add_argument("--ble-tx-uuid", default=MESHCORE_TX_UUID, help="TX characteristic UUID (device -> app)")
    parser.add_argument(
        "--debug-io",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Print TCP/BLE payloads to stderr (default: disabled)",
    )
    args = parser.parse_args()

    return RelayConfig(
        tcp_host=args.tcp_host,
        tcp_port=args.tcp_port,
        ble_address=args.ble_address,
        ble_rx_uuid=args.ble_rx_uuid,
        ble_tx_uuid=args.ble_tx_uuid,
        debug_io=args.debug_io,
    )


async def _main_async() -> int:
    relay = MeshcoreTcpBleRelay(parse_args())
    loop = asyncio.get_running_loop()
    shutdown_requested = False

    def _request_shutdown() -> None:
        nonlocal shutdown_requested
        if shutdown_requested:
            print("[warn] Second interrupt received, forcing exit")
            os._exit(130)
        shutdown_requested = True
        asyncio.create_task(relay.shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:
            pass

    await relay.run()
    return 0


def main() -> int:
    try:
        return asyncio.run(_main_async())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
