#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025-2026 Ed Kapitein
# Portions generated with AI assistance
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Scan for USB serial devices and identify MeshCore companion candidates.

Detection strategy (in order):
  1. VID:PID fingerprinting against a table of known MeshCore-compatible chips.
  2. Manufacturer / product / description name fragment matching.
  3. Active probe: send a DeviceQuery frame and verify a valid MeshCore response
     (only when --probe is given).
"""

import argparse
import sys
import time
from typing import Optional

import serial
import serial.tools.list_ports

MESHCORE_SERIAL_BAUD = 115200

TCP_FRAME_APP_TO_DEVICE = 0x3C  # '<'
TCP_FRAME_DEVICE_TO_APP = 0x3E  # '>'

# Known USB VID:PID combinations used by MeshCore-compatible boards.
# Format: (vid, pid, human-readable description)
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
    (0x2341, 0x0043, "Arduino Uno R3"),
    (0x1366, 0x1015, "Segger J-Link CDC (RAK / Nordic devkit)"),
    (0x2E8A, 0x000A, "Raspberry Pi RP2040 CDC (Pico / WisBlock RP2040)"),
]

# Substrings in device description / manufacturer / product that suggest MeshCore.
KNOWN_MESHCORE_NAME_FRAGMENTS = [
    "meshcore",
    "meshtastic",   # boards often dual-use
    "rak",
    "wisblock",
    "t-echo",
    "heltec",
    "lilygo",
    "t-beam",
    "lora",
]

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
# Helper: classify a port by VID/PID and name heuristics
# ---------------------------------------------------------------------------

def _classify_port(port) -> tuple[bool, str]:
    """Return (is_candidate, reason_string)."""
    if port.vid is not None and port.pid is not None:
        for vid, pid, desc in KNOWN_MESHCORE_VIDPID:
            if port.vid == vid and port.pid == pid:
                return True, desc

    combined = " ".join(filter(None, [
        port.description or "",
        port.manufacturer or "",
        port.product or "",
    ])).lower()
    for fragment in KNOWN_MESHCORE_NAME_FRAGMENTS:
        if fragment in combined:
            return True, f"name match: '{fragment}'"

    return False, ""


# ---------------------------------------------------------------------------
# Active probe
# ---------------------------------------------------------------------------

def _build_frame(payload: bytes) -> bytes:
    """Wrap payload in a MeshCore/TCP app-to-device frame."""
    length = len(payload)
    return bytes([TCP_FRAME_APP_TO_DEVICE, length & 0xFF, (length >> 8) & 0xFF]) + payload


def probe_device(device: str, baud: int = MESHCORE_SERIAL_BAUD, timeout: float = 1.5) -> Optional[bool]:
    """Probe a serial device for a MeshCore response.

    Returns:
        True   – device responded with a valid MeshCore frame
        False  – device did not respond within *timeout* seconds
        None   – device could not be opened (permission error, busy, etc.)
    """
    try:
        with serial.Serial(device, baud, timeout=0.1) as ser:
            ser.reset_input_buffer()
            # Send DeviceQuery (0x16)
            ser.write(_build_frame(bytes([0x16])))
            ser.flush()

            deadline = time.monotonic() + timeout
            buf = bytearray()

            while time.monotonic() < deadline:
                data = ser.read(128)
                if data:
                    buf.extend(data)
                    # Scan for a valid response frame ( '>' + len_lo + len_hi + payload )
                    i = 0
                    while i + 2 < len(buf):
                        if buf[i] == TCP_FRAME_DEVICE_TO_APP:
                            payload_len = buf[i + 1] | (buf[i + 2] << 8)
                            if payload_len > 0 and len(buf) >= i + 3 + payload_len:
                                return True
                        i += 1

            return False
    except serial.SerialException:
        return None


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def scan_devices(probe: bool = False) -> None:
    ports = sorted(serial.tools.list_ports.comports(), key=lambda p: p.device)

    if not ports:
        print("[info] No serial devices found.")
        return

    print(f"[info] Found {len(ports)} serial device(s)\n")

    results = []

    for port in ports:
        is_candidate, reason = _classify_port(port)
        probed: Optional[bool] = None

        if probe:
            print(f"[info] Probing {port.device}... ", end="", flush=True)
            probed = probe_device(port.device)
            if probed is True:
                print("✓ MeshCore companion detected")
                is_candidate = True
                if not reason:
                    reason = "probe confirmed"
            elif probed is False:
                print("no MeshCore response")
            else:
                print("could not open device")

        vid_pid = (
            f"{port.vid:04X}:{port.pid:04X}"
            if port.vid is not None and port.pid is not None
            else "----:----"
        )

        results.append({
            "port": port,
            "vid_pid": vid_pid,
            "is_candidate": is_candidate,
            "reason": reason,
            "probed": probed,
        })

    # ---- MeshCore candidates ----
    candidates = [r for r in results if r["is_candidate"]]
    if candidates:
        print("=== MeshCore Companion Candidates ===")
        for r in candidates:
            p = r["port"]
            probe_mark = " [probe ✓]" if r["probed"] is True else ""
            desc = (p.description or "(no description)")[:50]
            print(f"  {p.device:15s} | {r['vid_pid']:9s} | {desc}{probe_mark}")
            if r["reason"]:
                print(f"    → {r['reason']}")
        print()
    else:
        print("[info] No MeshCore companion candidates found by VID/PID or name.")
        if not probe:
            print("[hint] Run with --probe to actively query each device.\n")

    # ---- All devices ----
    print("=== All Serial Devices ===")
    for r in results:
        p = r["port"]
        marker = "★" if r["is_candidate"] else " "
        mfr = f" | mfr: {p.manufacturer}" if p.manufacturer else ""
        desc = (p.description or "(no description)")[:50]
        print(f"  {marker} {p.device:15s} | {r['vid_pid']:9s} | {desc}{mfr}")

    if candidates:
        print(f"\n[hint] Use --usb-device {candidates[0]['port'].device} with wifi2usb-bridge-relay.sh")
    else:
        print("\n[hint] Pass --usb-device /dev/ttyACM0 (or similar) to the relay, or use --usb-device auto")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scan for USB serial devices and identify MeshCore companion candidates"
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Actively probe each device by sending a MeshCore DeviceQuery (may briefly open/close ports)",
    )
    args = parser.parse_args()
    scan_devices(probe=args.probe)
