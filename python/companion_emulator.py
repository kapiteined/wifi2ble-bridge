#!/usr/bin/env python3
"""MeshCore companion emulator over TCP.

This emulator accepts framed MeshCore TCP packets from the Android app and
returns canned companion responses based on the traffic observed in logs.

Protocol framing:
- app -> companion: 0x3C + uint16le(payload_len) + payload
- companion -> app: 0x3E + uint16le(payload_len) + payload
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
import time
from dataclasses import dataclass
from typing import Optional

TCP_FRAME_APP_TO_DEVICE = 0x3C
TCP_FRAME_DEVICE_TO_APP = 0x3E

CMD_APP_START = 0x01
CMD_GET_DEVICE_TIME = 0x05
CMD_SET_DEVICE_TIME = 0x06
CMD_GET_CONTACTS = 0x04
CMD_SYNC_NEXT_MESSAGE = 0x0A
CMD_GET_CHANNEL = 0x1F
CMD_SET_CHANNEL = 0x20
CMD_GET_BATTERY_VOLTAGE = 0x14
CMD_DEVICE_QUERY = 0x16
CMD_GET_STATS = 0x38

RESP_SELF_INFO = 0x05
RESP_DEVICE_INFO = 0x0D
RESP_CURREN_TIME = 0x09
RESP_NO_MORE_MESSAGES = 0x0A
RESP_CONTACTS_START = 0x02
RESP_END_OF_CONTACTS = 0x04
RESP_OK = 0x00
RESP_ERR = 0x01
RESP_BATTERY_VOLTAGE = 0x0C
RESP_CHANNEL_INFO = 0x12
RESP_STATS = 0x18

DEVICE_INFO_RAW = bytes.fromhex(
    "0d0baf280000000031392d4170722d323032360048656c7465632054313134000000000000000000000000000000000000000000000000000000000076312e31352e302d6465653365323600000000000001"
)
SELF_INFO_RAW = bytes.fromhex(
    "05010216ed196399d243b7d6bc3a42a98ec566498ab9770b40d582e64fc12918f673fb884b461903029e420000001501f2440d0024f400000705f09f87b3f09f87b1204564204b6170697465696e"
)
BATTERY_VOLTAGE_RAW = bytes.fromhex(
    "0c5f101800000064000000"
)


@dataclass
class Config:
    host: str
    port: int
    debug_io: bool


class CompanionEmulator:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._server: Optional[asyncio.AbstractServer] = None
        self._shutdown_event = asyncio.Event()

    async def run(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, self.config.host, self.config.port)
        sockets = self._server.sockets or []
        for sock in sockets:
            print(f"[info] listening on {sock.getsockname()}")

        async with self._server:
            await self._shutdown_event.wait()

    async def shutdown(self) -> None:
        self._shutdown_event.set()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    def _log(self, direction: str, data: bytes) -> None:
        if not self.config.debug_io:
            return
        preview = data[:96].hex()
        if len(data) > 96:
            preview += "..."
        print(f"[debug] {direction} len={len(data)} hex={preview}", file=sys.stderr, flush=True)

    def _frame(self, payload: bytes) -> bytes:
        if len(payload) > 0xFFFF:
            raise ValueError("payload too large")
        return bytes((TCP_FRAME_DEVICE_TO_APP, len(payload) & 0xFF, (len(payload) >> 8) & 0xFF)) + payload

    def _build_curr_time(self) -> bytes:
        epoch_secs = int(time.time())
        return bytes((RESP_CURREN_TIME,)) + epoch_secs.to_bytes(4, "little", signed=False)

    def _build_battery_voltage(self) -> bytes:
        return BATTERY_VOLTAGE_RAW

    def _build_no_more_messages(self) -> bytes:
        return bytes((RESP_NO_MORE_MESSAGES,))

    def _build_ok(self) -> bytes:
        return bytes((RESP_OK,))

    def _build_err(self, code: int = 4) -> bytes:
        return bytes((RESP_ERR, code))

    async def _send(self, writer: asyncio.StreamWriter, payload: bytes) -> None:
        framed = self._frame(payload)
        self._log("companion->tcp", payload)
        self._log("companion->tcp(fr)", framed)
        writer.write(framed)
        await writer.drain()

    async def _handle_command(self, payload: bytes, writer: asyncio.StreamWriter) -> None:
        if not payload:
            return

        cmd = payload[0]
        self._log("tcp->companion", payload)

        if cmd == CMD_DEVICE_QUERY:
            await self._send(writer, DEVICE_INFO_RAW)
        elif cmd == CMD_APP_START:
            await self._send(writer, SELF_INFO_RAW)
        elif cmd == CMD_GET_DEVICE_TIME:
            epoch_secs = int(time.time())
            await self._send(writer, bytes((RESP_CURREN_TIME,)) + epoch_secs.to_bytes(4, "little", signed=False))
        elif cmd == CMD_GET_BATTERY_VOLTAGE:
            await self._send(writer, self._build_battery_voltage())
        elif cmd == CMD_GET_CONTACTS:
            # Return an empty contact list.
            await self._send(writer, bytes((RESP_CONTACTS_START,)) + (0).to_bytes(4, "little", signed=False))
            await self._send(writer, bytes((RESP_END_OF_CONTACTS,)) + (0).to_bytes(4, "little", signed=False))
        elif cmd == CMD_SYNC_NEXT_MESSAGE:
            await self._send(writer, self._build_no_more_messages())
        elif cmd == CMD_SET_DEVICE_TIME:
            await self._send(writer, self._build_ok())
        elif cmd == CMD_SET_CHANNEL:
            await self._send(writer, self._build_ok())
        elif cmd == CMD_GET_CHANNEL:
            channel_idx = payload[1] if len(payload) > 1 else 0
            name = f"Channel {channel_idx}".encode("utf-8")
            channel_payload = bytearray()
            channel_payload.append(RESP_CHANNEL_INFO)
            channel_payload.append(channel_idx)
            channel_payload.extend(name[:31])
            channel_payload.extend(b"\x00" * (32 - len(name[:31])))
            # 16-byte dummy secret to satisfy the client parser.
            channel_payload.extend(bytes.fromhex("00112233445566778899aabbccddeeff"))
            await self._send(writer, bytes(channel_payload))
        elif cmd == CMD_GET_STATS:
            # Minimal stats payload; enough for the app to proceed if it asks.
            stats_type = payload[1] if len(payload) > 1 else 0
            if stats_type == 0:
                stat_payload = bytes((RESP_STATS, stats_type)) + (4000).to_bytes(2, "little") + (12345).to_bytes(4, "little") + bytes((2,))
            elif stats_type == 1:
                stat_payload = bytes((RESP_STATS, stats_type)) + (-95).to_bytes(2, "little", signed=True) + (-70).to_bytes(1, "little", signed=True) + (8).to_bytes(1, "little", signed=True) + (111).to_bytes(4, "little") + (222).to_bytes(4, "little")
            else:
                stat_payload = bytes((RESP_STATS, stats_type)) + (1).to_bytes(4, "little") * 6
            await self._send(writer, stat_payload)
        else:
            # Generic OK so the app doesn't stall on unimplemented writes.
            await self._send(writer, self._build_ok())

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        print(f"[info] client connected: {peer}")
        buffer = bytearray()

        try:
            while True:
                chunk = await reader.read(512)
                if not chunk:
                    break
                self._log("tcp<-", chunk)
                buffer.extend(chunk)

                while True:
                    if len(buffer) < 3:
                        break
                    if buffer[0] != TCP_FRAME_APP_TO_DEVICE:
                        # Skip stray bytes until a valid frame marker is found.
                        del buffer[0]
                        continue

                    length = buffer[1] | (buffer[2] << 8)
                    frame_len = 3 + length
                    if len(buffer) < frame_len:
                        break

                    payload = bytes(buffer[3:frame_len])
                    del buffer[:frame_len]
                    await self._handle_command(payload, writer)
        finally:
            writer.close()
            await writer.wait_closed()
            print(f"[info] client disconnected: {peer}")


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description="MeshCore companion emulator")
    parser.add_argument("--host", default="0.0.0.0", help="TCP bind host")
    parser.add_argument("--port", type=int, default=5000, help="TCP bind port")
    parser.add_argument("--debug-io", action=argparse.BooleanOptionalAction, default=False, help="Log all packets to stderr")
    args = parser.parse_args()
    return Config(host=args.host, port=args.port, debug_io=args.debug_io)


async def _main() -> int:
    emulator = CompanionEmulator(parse_args())
    loop = asyncio.get_running_loop()

    def request_shutdown() -> None:
        asyncio.create_task(emulator.shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_shutdown)
        except NotImplementedError:
            pass

    await emulator.run()
    return 0


def main() -> int:
    try:
        return asyncio.run(_main())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
