# edge/raspberry/

Raspberry Pi node (Python): reads the DHT11, and an HX711 scale if one is wired, and publishes over MQTT, with the same topics and payloads as the ESP32 firmware ([messaging contract](../../docs/05-backend/04-messaging-contract.md)).

| File | Job |
|---|---|
| `pi_node/dht11.py` | Reads the sensor through the kernel IIO driver (no GPIO library, the kernel does the timing) |
| `pi_node/hx711.py` | Reads the scale over GPIO with libgpiod (optional) |
| `pi_node/payload.py` | Telemetry and status JSON, UUIDv7 `msg_id` |
| `pi_node/outbox.py` | SQLite outbox on the microSD: every message is stored before it is sent |
| `pi_node/uplink.py` | Sends the outbox over MQTT, oldest first, and marks a row sent only after the PUBACK |
| `pi_node/main.py` | Sampling loop, MQTT client with mutual TLS, last will, clean shutdown on SIGTERM |
| `config.example.toml` | Node settings |
| `systemd/smarthive-dht11.service` | Runs it at boot |

One telemetry message per sample, QoS 1. Each one is first written to the outbox (`/var/lib/smarthive/outbox.db`) with its exact bytes, connected or not, and leaves from there, oldest first. While the broker is unreachable the rows wait, also across restarts, and go out within about a second of the connection coming back. A row counts as sent only after the broker's PUBACK; a crash just before the mark sends it twice, and the server drops the repeat by its `msg_id`. Sent rows are deleted after `outbox_retention_days`; unsent rows are never deleted. `backend/tests/integration/test_node_outage.py` runs this code against a real broker that goes down, through to TimescaleDB. `clock_synced` comes from `timedatectl` (the Pi has no RTC).

## Setup on the Pi

1. Wiring: DHT11 DATA to GPIO 4 (pin 7), VCC to 3V3, GND to GND.
2. Enable the driver: add `dtoverlay=dht11,gpiopin=4` to `/boot/firmware/config.txt` and reboot. `cat /sys/bus/iio/devices/iio:device0/in_temp_input` should print milli-degrees.
3. Network: the OS handles it. Wi-Fi on Raspberry Pi OS Bookworm:
   ```bash
   sudo nmcli dev wifi connect "<SSID>" password "<password>"
   ```
4. Certificates: `infra/pki/gen_certs.sh node-0001`, then copy `ca.crt`, `node-0001.crt`, `node-0001.key` to `/etc/smarthive/certs/` (key `chmod 600`).
5. Install and run:
   ```bash
   sudo mkdir -p /opt/smarthive && sudo git clone <repo> /opt/smarthive   # or copy edge/raspberry
   python3 -m venv /opt/smarthive/venv
   /opt/smarthive/venv/bin/pip install -r /opt/smarthive/edge/raspberry/requirements.txt
   sudo cp config.example.toml /etc/smarthive/node.toml                     # edit node_id, host, cert paths
   cd /opt/smarthive/edge/raspberry && /opt/smarthive/venv/bin/python -m pi_node.main --config /etc/smarthive/node.toml
   ```
6. As a service: `sudo cp systemd/smarthive-dht11.service /etc/systemd/system/ && sudo systemctl enable --now smarthive-dht11`.

## Weight (optional)

The node publishes weight once the `[scale]` section is in its config (see `config.example.toml`): `quantity: weight` in kg on the same `telemetry` topic, every 300 s ([contract](../../docs/05-backend/04-messaging-contract.md#weight)). Not tried on hardware yet.

1. Wiring: HX711 VCC to 3V3 (not 5 V: the Pi's GPIO pins are not 5 V tolerant), GND to GND, DT to GPIO 5 (pin 29), SCK to GPIO 6 (pin 31). The load cell goes to E+, E-, A+, A-.
2. Permissions: `sudo usermod -aG gpio smarthive`.
3. Calibration, from `/opt/smarthive/edge/raspberry`, using the venv's Python:
   ```bash
   python -m pi_node.hx711 --dout 5 --sck 6    # scale empty: this is `offset`
   python -m pi_node.hx711 --dout 5 --sck 6    # known mass on it: this is `raw`
   ```
   `counts_per_kg = (raw - offset) / mass_in_kg`. Put both in `[scale]` and restart the service.

Python can be preempted while it clocks the chip, so one reading is the median of nine conversions. A failed reading goes out as `value: null, quality: read_error`.

## Tests

Run on any machine, with a fake sysfs folder instead of the sensor:

```bash
cd edge/raspberry
pip install -r requirements.txt pytest
python -m pytest
```
