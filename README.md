# mesh-emu

MeshCore TCP ↔ BLE relay tooling.

Deze repository bevat:

- een Python relay van TCP naar BLE: [python/meshcore_tcp_ble_relay.py](python/meshcore_tcp_ble_relay.py)
- een BLE scanner: [python/ble_scan.py](python/ble_scan.py)
- wrappers die automatisch een venv gebruiken:
	- [run_scan.sh](run_scan.sh)
	- [run_relay.sh](run_relay.sh)

## Snel starten

### 1) BLE devices scannen

```sh
./run_scan.sh
```

### 2) Relay starten

Optie A (via omgevingsvariabele):

```sh
BLE_ADDRESS="AA:BB:CC:DD:EE:FF" ./run_relay.sh
```

Optie B (via argument):

```sh
./run_relay.sh --ble-address AA:BB:CC:DD:EE:FF
```

Standaard luistert de relay op TCP poort `5000`.

## Handige opties

Voor extra logging:

```sh
./run_relay.sh --ble-address AA:BB:CC:DD:EE:FF --debug-io
```

Voor afsluiten: `Ctrl+C` stopt listener, actieve TCP sessie(s) en BLE sessie.

## Projectstructuur

- [python/](python/) Python scripts en requirements
- [src/](src/) C build artefacten / binary (`mesh-emu`)
- [start.sh](start.sh) legacy relay wrapper (functioneel, maar [run_relay.sh](run_relay.sh) is de voorkeursroute)

## Privacy / local config

Deze README bevat bewust geen lokale hostnames, companion namen of specifieke hardware-adressen.
Gebruik placeholders zoals `AA:BB:CC:DD:EE:FF` en vul lokaal je eigen waarden in.
