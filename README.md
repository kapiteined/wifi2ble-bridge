# MeshCore companion bridge

Relay tooling om een MeshCore companion te bridgen naar TCP, zodat een MeshCore
app over Wi-Fi verbinding kan maken met een lokaal aangesloten companion.

Twee transportmethodes worden ondersteund:

| Transport | Verbinding met companion | Scripts |
|-----------|--------------------------|---------|
| **BLE** | Bluetooth Low Energy (GATT) | `wifi2ble_bridge_*.sh` |
| **USB** | USB-serial (`/dev/ttyACM0` e.d.) | `wifi2usb_bridge_*.sh` |

Beide relays luisteren op TCP poort `5000` en zijn verder identiek in gebruik
vanuit de MeshCore app.

## Vereisten

- Python 3.x met `venv` en `pip`
  - Gentoo: `sudo emerge dev-python/pip`
  - Debian/Ubuntu: `sudo apt install python3-pip python3-venv`
  - Fedora/RHEL: `sudo dnf install python3-pip`
  - Arch: `sudo pacman -S python-pip`

---

## BLE bridge

De BLE bridge verbindt via Bluetooth Low Energy met de companion.

### 1) BLE devices scannen

```sh
./wifi2ble_bridge_scan.sh
```

### 2) Eenmalig pairen/trusten

**Eenmalig op de host:** eerst pairen/trusten met `bluetoothctl`.

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
- De companion werkt niet als `bluetoothctl` nog actief verbonden is.
- Zorg dat je na pair/trust expliciet `disconnect` doet voordat je de relay start.

### 3) BLE relay starten

Optie A (via omgevingsvariabele):

```sh
BLE_ADDRESS="AA:BB:CC:DD:EE:FF" ./wifi2ble_bridge_relay.sh
```

Optie B (via argument):

```sh
./wifi2ble_bridge_relay.sh --ble-address AA:BB:CC:DD:EE:FF
```

Extra logging: `--debug-io`

---

## USB bridge

De USB bridge verbindt via een USB-serial poort met de companion (typisch
`/dev/ttyACM0` voor ESP32- en nRF52840-gebaseerde boards).

### 1) USB devices scannen

```sh
./wifi2usb_bridge_scan.sh
```

Herkent automatisch bekende MeshCore-chips op VID:PID (CP210x, CH340, CH343,
FT232, nRF52840, RP2040, ...) en boardnamen (RAK, Heltec, LilyGO, T-Echo, ...).

Met actieve probe (stuurt een DeviceQuery naar elk gevonden device):

```sh
./wifi2usb_bridge_scan.sh --probe
```

### 2) USB relay starten

Automatische detectie (standaard):

```sh
./wifi2usb_bridge_relay.sh
```

Of met expliciet device:

```sh
./wifi2usb_bridge_relay.sh --usb-device /dev/ttyACM0
```

Extra logging: `--debug-io`

> **Rechten:** als de relay `Permission denied` geeft, voeg de gebruiker toe aan
> de `dialout` groep: `sudo usermod -aG dialout $USER` (opnieuw inloggen vereist).

---

## Installeren onder Linux

```sh
sudo ./install.sh
```

Of met een eigen prefix:

```sh
sudo ./install.sh --prefix /opt/meshcore-bridge
```

Na installatie:

```
/usr/local/bin/wifi2ble-bridge-scan.sh
/usr/local/bin/wifi2ble-bridge-relay.sh
/usr/local/bin/wifi2usb-bridge-scan.sh
/usr/local/bin/wifi2usb-bridge-relay.sh
```

## Automatisch starten met systemd

`install.sh` installeert beide systemd units en bijbehorende environment files.

### BLE service

```sh
sudo nano /etc/default/wifi2ble-bridge-relay
# Zet: BLE_ADDRESS=AA:BB:CC:DD:EE:FF

sudo systemctl enable --now wifi2ble-bridge-relay.service
```

### USB service

```sh
sudo nano /etc/default/wifi2usb-bridge-relay
# USB_DEVICE=auto  (auto-detectie op VID:PID, standaard)
# of:
# USB_DEVICE=/dev/ttyACM0

sudo systemctl enable --now wifi2usb-bridge-relay.service
```

Status en logs:

```sh
systemctl status wifi2ble-bridge-relay.service
journalctl -u wifi2ble-bridge-relay.service -f

systemctl status wifi2usb-bridge-relay.service
journalctl -u wifi2usb-bridge-relay.service -f
```

## Projectstructuur

```
python/
  wifi2ble_bridge_scan.py     BLE scanner
  wifi2ble_bridge_relay.py    TCP ↔ BLE relay
  wifi2usb_bridge_scan.py     USB scanner
  wifi2usb_bridge_relay.py    TCP ↔ USB relay
  requirements.txt            BLE dependencies (bleak)
  requirements_usb.txt        USB dependencies (pyserial)
systemd/
  wifi2ble-bridge-relay.service
  wifi2ble-bridge-relay.env
  wifi2usb-bridge-relay.service
  wifi2usb-bridge-relay.env
install.sh                    Linux installer (prefix-based)
```

## Privacy / local config

Deze README bevat bewust geen lokale hostnames, companion namen of specifieke
hardware-adressen. Gebruik placeholders zoals `AA:BB:CC:DD:EE:FF` en vul lokaal
je eigen waarden in.
