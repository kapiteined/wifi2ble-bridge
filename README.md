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

**Belangrijk (eenmalig op de Raspberry Pi): eerst pairen/trusten met `bluetoothctl`.**

Voorbeeld:

```sh
bluetoothctl
power on
agent on
default-agent
pair AA:BB:CC:DD:EE:FF
trust AA:BB:CC:DD:EE:FF
disconnect AA:BB:CC:DD:EE:FF
quit
```

Let op:
- De companion werkt niet als `bluetoothctl` nog actief connected is met de companion.
- Zorg dat je na pair/trust expliciet `disconnect` doet in `bluetoothctl` voordat je de relay start.

Optie A (via omgevingsvariabele):

```sh
BLE_ADDRESS="AA:BB:CC:DD:EE:FF" ./run_relay.sh
```

Optie B (via argument):

```sh
./run_relay.sh --ble-address AA:BB:CC:DD:EE:FF
```

Standaard luistert de relay op TCP poort `5000`.

## Installeren onder Linux

Gebruik de installer om alles onder een prefix te plaatsen (standaard `/usr/local`):

```sh
./install.sh
```

Of met een eigen prefix:

```sh
./install.sh --prefix /opt/mesh-emu
```

Na installatie zijn dit de commando's:

- `/usr/local/bin/mesh-emu-scan`
- `/usr/local/bin/mesh-emu-relay`

Deze launchers gebruiken een venv onder `/usr/local/lib/mesh-emu/.venv`.

## Handige opties

Voor extra logging:

```sh
./run_relay.sh --ble-address AA:BB:CC:DD:EE:FF --debug-io
```

Voor afsluiten: `Ctrl+C` stopt listener, actieve TCP sessie(s) en BLE sessie.

## Projectstructuur

- [python/](python/) Python scripts en requirements
- [src/](src/) C build artefacten / binary (`mesh-emu`)
- [install.sh](install.sh) Linux installer (prefix-based)

## Privacy / local config

Deze README bevat bewust geen lokale hostnames, companion namen of specifieke hardware-adressen.
Gebruik placeholders zoals `AA:BB:CC:DD:EE:FF` en vul lokaal je eigen waarden in.
