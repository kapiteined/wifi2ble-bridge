# BLE Bridge Mode Setup

## Companion Device Found
- **Address**: C5:8B:5B:F7:BB:BC
- **Name**: MeshCore-🇳🇱 Ed Kapitein

## Relay Running in BLE Bridge Mode
The relay is now listening on TCP port 5000 and bridging to the BLE companion device.

**Flow:**
1. Android MeshCore app connects to TCP 0.0.0.0:5000
2. App sends DeviceQuery command
3. Relay forwards the command to BLE RX characteristic
4. BLE companion processes and sends response via TX characteristic
5. Relay forwards BLE response back to TCP app

## Next Steps
1. Open Android MeshCore app
2. Configure to connect to your device (phone) IP at port 5000
3. App will send commands, relay will forward them to the real companion
4. All communication will be logged with hex dumps for debugging

## Debug Output Location
Terminal: e616cbf9-f0e6-4762-b683-d4efa9a271e7

Watch for:
- `[info] TCP client connected:` - App connected
- `[info] app command: DeviceQuery` - Command received
- `[debug] Sent to BLE RX:` - Forwarded to companion
- `[debug] BLE->` - Response from companion
- Hex dumps for all payloads

## Companion BLE Device Details
- Service UUID: 6E400001-B5A3-F393-E0A9-E50E24DCCA9E
- RX Characteristic: 6E400002-B5A3-F393-E0A9-E50E24DCCA9E (app → device)
- TX Characteristic: 6E400003-B5A3-F393-E0A9-E50E24DCCA9E (device → app)
