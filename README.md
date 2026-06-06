# wifi2ble-bridge

MeshCore TCP ↔ BLE relay tooling.

Deze repository bevat:

- een Python relay van TCP naar BLE: [python/wifi2ble_bridge_relay.py](python/wifi2ble_bridge_relay.py)
- een BLE scanner: [python/wifi2ble_bridge_scan.py](python/wifi2ble_bridge_scan.py)
- wrappers die automatisch een venv gebruiken:
  - [wifi2ble_bridge_scan.sh](wifi2ble_bridge_scan.sh)
  - [wifi2ble_bridge_relay.sh](wifi2ble_bridge_relay.sh)
### 1) BLE devices scannen

```sh
./wifi2ble_bridge_scan.sh
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
BLE_ADDRESS="AA:BB:CC:DD:EE:FF" ./wifi2ble_bridge_relay.sh
```

Optie B (via argument):

```sh
./wifi2ble_bridge_relay.sh --ble-address AA:BB:CC:DD:EE:FF
```

Standaard luistert de relay op TCP poort `5000`.

## Installeren onder Linux

Gebruik de installer om alles onder een prefix te plaatsen (standaard `/usr/local`):

```sh
sudo ./install.sh
```

Of met een eigen prefix:

```sh
sudo ./install.sh --prefix /opt/wifi2ble-bridge
```

Na installatie zijn dit de commando's:

- `/usr/local/bin/wifi2ble-bridge-scan.sh`
- `/usr/local/bin/wifi2ble-bridge-relay.sh`

Deze launchers gebruiken een venv onder `/usr/local/lib/wifi2ble-bridge/.venv`.

## Handige opties

Voor extra logging:

```sh
./wifi2ble_bridge_relay.sh --ble-address AA:BB:CC:DD:EE:FF --debug-io
```

Voor afsluiten: `Ctrl+C` stopt listener, actieve TCP sessie(s) en BLE sessie.

## Automatisch starten met systemd

`install.sh` installeert de systemd unit en de environment file automatisch (vereist root).

**Belangrijk:** stel daarna het BLE-adres in vóór je de service start:

```sh
sudo nano /etc/default/wifi2ble-bridge-relay
# Zet: BLE_ADDRESS=AA:BB:CC:DD:EE:FF
```

Vervolgens de service activeren:

```sh
sudo systemctl enable --now wifi2ble-bridge-relay.service
```

Status en logs bekijken:

```sh
systemctl status wifi2ble-bridge-relay.service
journalctl -u wifi2ble-bridge-relay.service -f
```

## Projectstructuur

- [python/](python/) Python scripts en requirements
- [install.sh](install.sh) Linux installer (prefix-based)
- [systemd/](systemd/) systemd unit en env-bestand

## Privacy / local config

Deze README bevat bewust geen lokale hostnames, companion namen of specifieke hardware-adressen.
Gebruik placeholders zoals `AA:BB:CC:DD:EE:FF` en vul lokaal je eigen waarden in.
