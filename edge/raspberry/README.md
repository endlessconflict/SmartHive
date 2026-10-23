# edge/raspberry/

Raspberry Pi node (Python): reads the DHT11 and publishes temperature and humidity over MQTT, with the same topics and payloads as the ESP32 firmware ([messaging contract](../../docs/05-backend/04-messaging-contract.md)).

| File | Job |
|---|---|
| `pi_node/dht11.py` | Reads the sensor through the kernel IIO driver (no GPIO library, the kernel does the timing) |
| `pi_node/payload.py` | Telemetry and status JSON, UUIDv7 `msg_id` |
| `pi_node/main.py` | Sampling loop, MQTT client with mutual TLS, last will, clean shutdown on SIGTERM |
| `config.example.toml` | Node settings |
| `systemd/smarthive-dht11.service` | Runs it at boot |

One telemetry message per reading, QoS 1. While the broker is unreachable, paho keeps them queued in memory (`max_pending`) and delivers them on reconnect; they are lost if the process restarts. `clock_synced` comes from `timedatectl` (the Pi has no RTC).

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

## Tests

Run on any machine, with a fake sysfs folder instead of the sensor:

```bash
cd edge/raspberry
pip install -r requirements.txt pytest
python -m pytest
```
