#!/usr/bin/env python3
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
import signal
import sys
from dataclasses import dataclass
from typing import Optional

from bleak import BleakClient, BleakScanner

MESHCORE_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
MESHCORE_RX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # app -> firmware
MESHCORE_TX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # firmware -> app
TCP_FRAME_APP_TO_DEVICE = 0x3C  # '<'
TCP_FRAME_DEVICE_TO_APP = 0x3E  # '>'
PACKET_DEVICE_INFO = 0x0D

RESP_SELF_INFO_RAW = bytes.fromhex(
    "05010216ed196399d243b7d6bc3a42a98ec566498ab9770b40d582e64fc12918f673fb884b461903029e420000001501f2440d0024f400000705f09f87b3f09f87b1204564204b6170697465696e"
)
RESP_DEVICE_INFO_RAW = bytes.fromhex(
    "0d0baf280000000031392d4170722d323032360048656c7465632054313134000000000000000000000000000000000000000000000000000000000076312e31352e302d6465653365323600000000000001"
)
RESP_BATTERY_VOLTAGE_RAW = bytes.fromhex(
    "0c5f101800000064000000"
)
RESP_CONTACTS_START_RAW = bytes((0x02, 0x00, 0x00, 0x00, 0x00))
RESP_END_OF_CONTACTS_RAW = bytes((0x04, 0x00, 0x00, 0x00, 0x00))
RESP_NO_MORE_MESSAGES_RAW = bytes((0x0A,))
RESP_OK_RAW = bytes((0x00,))

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
    ble_service_uuid: str
    startup_check: bool
    debug_io: bool
    tcp_meshcore_framing: bool
    session_bootstrap: bool
    tcp_response_mode: str
    normalize_device_info: bool


class MeshcoreTcpBleRelay:
    def __init__(self, config: RelayConfig) -> None:
        self.config = config
        self._server: Optional[asyncio.AbstractServer] = None
        self._shutdown_event = asyncio.Event()
        self._active_client_lock = asyncio.Lock()

    async def run(self) -> None:
        if self.config.startup_check:
            await self._startup_check()

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

    async def shutdown(self) -> None:
        self._shutdown_event.set()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

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
            print(f"[info] TCP client connected: {peer}")
            try:
                await self._run_client_session(reader, writer)
            except Exception as exc:  # broad by design for long-running relay
                print(f"[error] session failure: {exc}")
            finally:
                writer.close()
                await writer.wait_closed()
                print(f"[info] TCP client disconnected: {peer}")

    async def _startup_check(self) -> None:
        print("[info] Running startup BLE check")

        max_retries = 3
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                target = await self._resolve_ble_target()
                async with BleakClient(target, timeout=10.0) as ble:
                    print(f"[info] BLE connected for startup check: {self.config.ble_address}")
                    await self._validate_required_characteristics(ble)

                    print("[info] BLE characteristics verified; no startup commands sent")
                return  # success
            except Exception as exc:
                last_error = exc
                if attempt < max_retries:
                    print(f"[warn] BLE check attempt {attempt} failed: {exc}, retrying in 2s...")
                    await asyncio.sleep(2)
                else:
                    print(f"[warn] startup BLE check failed after {max_retries} attempts: {last_error}")

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
        framed_payload = self._frame_tcp_payload(payload) if self.config.tcp_meshcore_framing else payload
        self._debug_log_io("TCP->", framed_payload)
        writer.write(framed_payload)

    def _build_curr_time_payload(self) -> bytes:
        import time

        epoch_secs = int(time.time())
        return bytes((0x09,)) + epoch_secs.to_bytes(4, "little", signed=False)

    def _build_probe_response(self, command: int, payload: bytes) -> list[bytes]:
        if command == 0x01:
            return [RESP_SELF_INFO_RAW]
        if command == 0x16:
            return [RESP_DEVICE_INFO_RAW]
        if command == 0x14:
            return [RESP_BATTERY_VOLTAGE_RAW]
        if command == 0x04:
            return [RESP_CONTACTS_START_RAW, RESP_END_OF_CONTACTS_RAW]
        if command == 0x05:
            return [self._build_curr_time_payload()]
        if command == 0x06:
            return [RESP_OK_RAW]
        if command == 0x0A:
            return [RESP_NO_MORE_MESSAGES_RAW]
        return [RESP_OK_RAW]

    def _encode_tcp_payload(self, payload: bytes) -> bytes:
        if not self.config.tcp_meshcore_framing:
            return payload

        return self._frame_tcp_payload(payload)

    def _normalize_ble_packet_for_tcp(self, payload: bytes) -> bytes:
        if not self.config.normalize_device_info:
            return payload

        if len(payload) < 2 or payload[0] != PACKET_DEVICE_INFO:
            return payload

        # Legacy app compatibility:
        # - build date may be parsed as "dd MMM yyyy" (spaces, not dashes)
        # - compact model/version to avoid large null-padded tails.
        out = bytearray(payload)

        # DeviceInfo layout starts with:
        # [0]=0x0D, [1]=fw_ver, [2:8]=reserved, [8:20]=build date c-string area
        for idx in range(8, min(20, len(out))):
            if out[idx] == 0x2D:  # '-'
                out[idx] = 0x20  # ' '

        # For fw >= 3, firmware often returns model/version as fixed-width
        # null-padded fields. Convert to compact tail text.
        if len(out) >= 80:
            model = bytes(out[20:60]).split(b"\x00", 1)[0].decode("utf-8", errors="ignore").strip()
            version = bytes(out[60:80]).split(b"\x00", 1)[0].decode("utf-8", errors="ignore").strip()
            tail = f"{model} {version}".strip().encode("utf-8")
            out = bytearray(out[:20] + tail)

        return bytes(out)

    def _decode_tcp_payloads(self, rx_buffer: bytearray, chunk: bytes) -> list[bytes]:
        if not self.config.tcp_meshcore_framing:
            return [chunk]

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

    def _format_device_info(self, packet: bytes) -> str:
        if len(packet) < 2:
            return "invalid packet"

        fw_ver = packet[1]
        if fw_ver >= 3 and len(packet) >= 80:
            max_contacts = packet[2] * 2
            max_channels = packet[3]
            model = packet[20:60].decode("utf-8", errors="ignore").rstrip("\x00").strip()
            version = packet[60:80].decode("utf-8", errors="ignore").rstrip("\x00").strip()
            return (
                f"fw_ver={fw_ver}, max_contacts={max_contacts}, "
                f"max_channels={max_channels}, model='{model}', version='{version}'"
            )

        return f"fw_ver={fw_ver}, len={len(packet)}"

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
            async with BleakClient(self.config.ble_address) as ble_client:
                print(f"[info] Connected to BLE companion")

                ble_rx_queue = asyncio.Queue()

                def on_ble_notification(sender, data):
                    """Non-async BLE callback; queue for async handler."""
                    try:
                        ble_rx_queue.put_nowait(data)
                    except asyncio.QueueFull:
                        print("[warn] BLE RX queue full, dropping notification")

                await ble_client.start_notify(self.config.ble_tx_uuid, on_ble_notification)

                tcp_rx_buffer = bytearray()
                ble_send_pending = False

                # Background task to relay BLE RX -> TCP
                async def ble_to_tcp_relay():
                    while True:
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
                    while True:
                        chunk = await reader.read(512)
                        if not chunk:
                            print("[debug] TCP read returned empty, client closed connection")
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
                            print(f"[info] app command: {command_name} ({command_code:#04x})")

                            # Forward to BLE
                            self._debug_log_io("BLE<-", payload)
                            await ble_client.write_gatt_char(self.config.ble_rx_uuid, payload, response=False)
                            print(f"[debug] Sent to BLE RX: {payload.hex()}")

                finally:
                    relay_task.cancel()
                    try:
                        await relay_task
                    except asyncio.CancelledError:
                        pass
                    await ble_client.stop_notify(self.config.ble_tx_uuid)

        except Exception as e:
            print(f"[error] BLE bridge error: {e}")
            import traceback
            traceback.print_exc()

    async def _resolve_ble_target(self):
        devices = await BleakScanner.discover(timeout=6.0, return_adv=True)
        for device, _ in devices.values():
            if device.address.upper() == self.config.ble_address.upper():
                return device
        raise RuntimeError(
            f"BLE device not found in scan: {self.config.ble_address} "
            "(ensure it is advertising and in range)"
        )

    async def _validate_required_characteristics(self, ble: BleakClient) -> None:
        services = ble.services
        service = services.get_service(self.config.ble_service_uuid)
        if service is None:
            raise RuntimeError(f"MeshCore service not found: {self.config.ble_service_uuid}")

        rx_char = services.get_characteristic(self.config.ble_rx_uuid)
        tx_char = services.get_characteristic(self.config.ble_tx_uuid)
        if rx_char is None:
            raise RuntimeError(f"RX characteristic not found: {self.config.ble_rx_uuid}")
        if tx_char is None:
            raise RuntimeError(f"TX characteristic not found: {self.config.ble_tx_uuid}")


def parse_args() -> RelayConfig:
    parser = argparse.ArgumentParser(description="MeshCore TCP to BLE GATT relay")
    parser.add_argument("--tcp-host", default="0.0.0.0", help="TCP bind host (default: 0.0.0.0)")
    parser.add_argument("--tcp-port", type=int, default=5000, help="TCP bind port (default: 5000)")
    parser.add_argument("--ble-address", default="", help="BLE MAC address of the companion (optional in probe mode)")
    parser.add_argument("--ble-service-uuid", default=MESHCORE_SERVICE_UUID, help="MeshCore BLE service UUID")
    parser.add_argument("--ble-rx-uuid", default=MESHCORE_RX_UUID, help="RX characteristic UUID (app -> device)")
    parser.add_argument("--ble-tx-uuid", default=MESHCORE_TX_UUID, help="TX characteristic UUID (device -> app)")
    parser.add_argument(
        "--startup-check",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Run BLE SELF_INFO/DEVICE_INFO check at startup (default: disabled)",
    )
    parser.add_argument(
        "--debug-io",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Print TCP/BLE payloads to stderr (default: disabled)",
    )
    parser.add_argument(
        "--tcp-meshcore-framing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Decode/encode MeshCore TCP framing (default: enabled)",
    )
    parser.add_argument(
        "--session-bootstrap",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Send APP_START on BLE connect for each TCP session (default: enabled)",
    )
    parser.add_argument(
        "--tcp-response-mode",
        choices=("framed", "raw", "both"),
        default="framed",
        help="Encoding for BLE->TCP responses (default: framed)",
    )
    parser.add_argument(
        "--normalize-device-info",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Normalize DEVICE_INFO payload for client compatibility (default: disabled)",
    )
    args = parser.parse_args()

    return RelayConfig(
        tcp_host=args.tcp_host,
        tcp_port=args.tcp_port,
        ble_address=args.ble_address,
        ble_rx_uuid=args.ble_rx_uuid,
        ble_tx_uuid=args.ble_tx_uuid,
        ble_service_uuid=args.ble_service_uuid,
        startup_check=args.startup_check,
        debug_io=args.debug_io,
        tcp_meshcore_framing=args.tcp_meshcore_framing,
        session_bootstrap=args.session_bootstrap,
        tcp_response_mode=args.tcp_response_mode,
        normalize_device_info=args.normalize_device_info,
    )


async def _main_async() -> int:
    relay = MeshcoreTcpBleRelay(parse_args())
    loop = asyncio.get_running_loop()

    def _request_shutdown() -> None:
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
