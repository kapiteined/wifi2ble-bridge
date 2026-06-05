# mesh-emu

`mesh-emu` is a C project for a MeshCore companion relay that runs on one Raspberry Pi: it accepts a TCP connection and forwards the data to a Bluetooth companion endpoint.

## Intended Flow

- Android MeshCore client connects to the Pi over TCP on port `5000` by default
- the Pi forwards received data to the companion over Bluetooth
- Bluetooth is currently configured as an RFCOMM client endpoint

## Status

This repository currently contains a minimal Autotools/Automake skeleton and starter modules for the app, bridge, and logging layers.

## Layout

- `src/` - program sources
- `include/mesh_emu/` - public project headers

## Build

```sh
autoreconf -fi
./configure
make
```

## Run

```sh
./src/mesh-emu
```

## Companion Emulator

If you only want to emulate the companion side for the Android app, run the TCP emulator:

```sh
cd python
python companion_emulator.py --host 0.0.0.0 --port 5000 --debug-io
```

It accepts framed MeshCore TCP traffic and returns canned `DeviceInfo` / `SelfInfo` responses.

## Next Steps

- replace the RFCOMM placeholder address with your companion MAC address
- add framing if the companion protocol needs packet boundaries
- make the Bluetooth endpoint configurable from the command line
