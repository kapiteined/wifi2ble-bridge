#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025-2026 Ed Kapitein
# Portions generated with AI assistance
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Single-Pi MeshCore companion relay (USB/Serial).

Flow:
- Accept one TCP client (Android / desktop MeshCore app)
- Connect to MeshCore companion over USB serial (ttyACM0, ttyUSB0, or auto-detected)
- Forward TCP <-> Serial bidirectionally

Both sides use the same '<'/'>' frame protocol (MeshCore over USB is framed
identically to the TCP wire format), so the relay is a transparent byte pipe.
Frames are parsed only when --debug-io is enabled, to log each command/response.

Requires pyserial and pyserial-asyncio.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from dataclasses import dataclass
from typing import Optional

import serial
import serial.tools.list_ports
import serial_asyncio  # pyserial-asyncio

TCP_FRAME_APP_TO_DEVICE = 0x3C  # '<'
TCP_FRAME_DEVICE_TO_APP = 0x3E  # '>'

MESHCORE_SERIAL_BAUD = 115200

# ---- companion auto-detection ----

KNOWN_MESHCORE_VIDPID: list[tuple[int, int, str]] = [
    (0x10C4, 0xEA60, "Silicon Labs CP210x (ESP32 / T-Beam / Heltec / TTGO)"),
    (0x1A86, 0x7523, "WCH CH340 (common ESP32 boards)"),
    (0x1A86, 0x55D4, "WCH CH343 (newer ESP32 boards)"),
    (0x1A86, 0x7522, "WCH CH340K"),
    (0x0403, 0x6001, "FTDI FT232R"),
    (0x0403, 0x6015, "FTDI FT230X"),
    (0x239A, 0x0029, "Adafruit nRF52840 Feather (T-Echo compatible)"),
    (0x239A, 0x8029, "Adafruit nRF52840 UF2 bootloader"),
    (0x1915, 0x520F, "Nordic Semiconductor nRF52840 USB CDC"),
    (0x1915, 0x5210, "Nordic Semiconductor nRF52840 USB CDC (alt)"),
    (0x1366, 0x1015, "Segger J-Link CDC (RAK / Nordic devkit)"),
    (0x2E8A, 0x000A, "Raspberry Pi RP2040 CDC"),
]

KNOWN_MESHCORE_NAME_FRAGMENTS = [
    "meshcore",
    "meshtastic",
    "rak",
    "wisblock",
    "t-echo",
    "heltec",
    "lilygo",
    "t-beam",
    "lora",
]

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


# ---------------------------------------------------------------------------
# Companion auto-detection
# ---------------------------------------------------------------------------

def find_companion_device() -> Optional[str]:
    """Auto-detect a MeshCore companion USB serial device.

    Heuristic order:
      1. VID:PID match against known MeshCore-compatible chips.
      2. Name fragment match in description / manufacturer / product.
      3. First ttyACM* or ttyUSB* device (last-resort fallback).

    Returns the device path (e.g. '/dev/ttyACM0') or None.
    """
    ports = sorted(serial.tools.list_ports.comports(), key=lambda p: p.device)

    for port in ports:
        if port.vid is not None and port.pid is not None:
            for vid, pid, desc in KNOWN_MESHCORE_VIDPID:
                if port.vid == vid and port.pid == pid:
                    print(f"[info] Auto-detect: matched VID:PID {port.vid:04X}:{port.pid:04X} → {desc}")
                    return port.device

        combined = " ".join(filter(None, [
            port.description or "",
            port.manufacturer or "",
            port.product or "",
        ])).lower()
        for fragment in KNOWN_MESHCORE_NAME_FRAGMENTS:
            if fragment in combined:
                print(f"[info] Auto-detect: name match '{fragment}' on {port.device}")
                return port.device

    # Last-resort: take first CDC-ACM or USB-serial device
    for port in ports:
        dev = port.device
        if "/dev/ttyACM" in dev or "/dev/ttyUSB" in dev:
            print(f"[info] Auto-detect: fallback to first USB serial device {dev}")
            return dev

    return None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class RelayConfig:
    tcp_host: str
    tcp_port: int
    usb_device: str   # path like /dev/ttyACM0, or the string "auto"
    usb_baud: int
    debug_io: bool


# ---------------------------------------------------------------------------
# Relay
# ---------------------------------------------------------------------------

class MeshcoreTcpUsbRelay:
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

            client_tasks = [t for t in self._client_tasks if not t.done()]
            for task in client_tasks:
                task.cancel()
            if client_tasks:
                await asyncio.gather(*client_tasks, return_exceptions=True)

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
            print(f"[info] TCP client connected: {peer}")
            try:
                await self._run_client_session(reader, writer)
            except Exception as exc:
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

    # ---- debug frame logging ----

    def _log_io(self, direction: str, data: bytes) -> None:
        if not self.config.debug_io:
            return
        preview = data[:96].hex()
        if len(data) > 96:
            preview += "..."
        print(f"[debug] {direction} len={len(data)} hex={preview}", file=sys.stderr, flush=True)

    def _decode_frames_for_log(self, buf: bytearray, chunk: bytes) -> list[tuple[int, bytes]]:
        """Parse complete frames from *chunk* into *buf*. Returns (frame_type, payload) pairs.
        Used only when debug_io is enabled; does not affect the actual data path."""
        buf.extend(chunk)
        result: list[tuple[int, bytes]] = []

        while len(buf) >= 3:
            frame_type = buf[0]
            if frame_type not in (TCP_FRAME_APP_TO_DEVICE, TCP_FRAME_DEVICE_TO_APP):
                self._debug(f"Unexpected frame byte 0x{frame_type:02x} in log buffer, resyncing")
                buf.clear()
                break
            payload_len = buf[1] | (buf[2] << 8)
            if len(buf) < 3 + payload_len:
                break
            result.append((frame_type, bytes(buf[3:3 + payload_len])))
            del buf[:3 + payload_len]

        return result

    # ---- client session ----

    async def _run_client_session(
        self,
        tcp_reader: asyncio.StreamReader,
        tcp_writer: asyncio.StreamWriter,
    ) -> None:
        """Bridge TCP client <-> USB serial companion device."""

        # Resolve device path
        device = self.config.usb_device
        if device == "auto":
            device = find_companion_device()
            if device is None:
                print("[error] Could not auto-detect a MeshCore companion USB device.")
                print("[hint]  Run wifi2usb-bridge-scan.sh to list available devices.")
                print("[hint]  Pass --usb-device /dev/ttyACM0 (or similar) explicitly.")
                return
            print(f"[info] Auto-detected companion device: {device}")

        print(f"[info] Opening {device} at {self.config.usb_baud} baud")
        try:
            serial_reader, serial_writer = await serial_asyncio.open_serial_connection(
                url=device,
                baudrate=self.config.usb_baud,
            )
        except serial.SerialException as exc:
            print(f"[error] Failed to open {device}: {exc}")
            print("[hint]  Check device permissions: sudo usermod -aG dialout $USER  (re-login required)")
            return

        print(f"[info] Connected to USB companion on {device}")

        # Separate log-only buffers for debug frame parsing (not part of the data path)
        tcp_log_buf: bytearray = bytearray()
        serial_log_buf: bytearray = bytearray()

        # TCP -> serial
        async def tcp_to_serial() -> None:
            while not self._shutdown_event.is_set():
                try:
                    chunk = await asyncio.wait_for(tcp_reader.read(512), timeout=0.1)
                    if not chunk:
                        self._debug("TCP EOF – client closed connection")
                        break
                    if self.config.debug_io:
                        for frame_type, payload in self._decode_frames_for_log(tcp_log_buf, chunk):
                            cmd = payload[0] if payload else None
                            name = COMMAND_NAMES.get(cmd, f"0x{cmd:02x}") if cmd is not None else "?"
                            self._log_io(f"TCP->serial cmd={name}({len(payload)}B)", payload)
                    serial_writer.write(chunk)
                    await serial_writer.drain()
                except asyncio.TimeoutError:
                    pass
                except Exception as exc:
                    if not self._shutdown_event.is_set():
                        print(f"[warn] TCP->serial relay error: {exc}")
                    break

        # Serial -> TCP
        async def serial_to_tcp() -> None:
            while not self._shutdown_event.is_set():
                try:
                    chunk = await asyncio.wait_for(serial_reader.read(512), timeout=0.1)
                    if not chunk:
                        self._debug("Serial EOF")
                        break
                    if self.config.debug_io:
                        for frame_type, payload in self._decode_frames_for_log(serial_log_buf, chunk):
                            resp = payload[0] if payload else None
                            name = RESPONSE_NAMES.get(resp, f"0x{resp:02x}") if resp is not None else "?"
                            self._log_io(f"serial->TCP resp={name}({len(payload)}B)", payload)
                    tcp_writer.write(chunk)
                    await tcp_writer.drain()
                except asyncio.TimeoutError:
                    pass
                except Exception as exc:
                    if not self._shutdown_event.is_set():
                        print(f"[warn] serial->TCP relay error: {exc}")
                    break

        t2s = asyncio.create_task(tcp_to_serial())
        s2t = asyncio.create_task(serial_to_tcp())

        try:
            _done, pending = await asyncio.wait(
                [t2s, s2t],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        finally:
            serial_writer.close()
            self._debug(f"Serial port {device} closed")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> RelayConfig:
    parser = argparse.ArgumentParser(description="MeshCore TCP to USB serial relay")
    parser.add_argument(
        "--tcp-host",
        default="0.0.0.0",
        help="TCP bind host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--tcp-port",
        type=int,
        default=5000,
        help="TCP bind port (default: 5000)",
    )
    parser.add_argument(
        "--usb-device",
        default="auto",
        metavar="DEVICE",
        help=(
            "USB serial device path (e.g. /dev/ttyACM0) "
            "or 'auto' to auto-detect by VID/PID (default: auto)"
        ),
    )
    parser.add_argument(
        "--usb-baud",
        type=int,
        default=MESHCORE_SERIAL_BAUD,
        help=f"Serial baud rate (default: {MESHCORE_SERIAL_BAUD})",
    )
    parser.add_argument(
        "--debug-io",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Print TCP/serial frame payloads to stderr (default: disabled)",
    )
    args = parser.parse_args()

    return RelayConfig(
        tcp_host=args.tcp_host,
        tcp_port=args.tcp_port,
        usb_device=args.usb_device,
        usb_baud=args.usb_baud,
        debug_io=args.debug_io,
    )


async def _main_async() -> int:
    relay = MeshcoreTcpUsbRelay(parse_args())
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
