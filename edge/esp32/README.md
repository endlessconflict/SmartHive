# edge/esp32/

ESP32 firmware (ESP-IDF, C): reads a DHT11, joins Wi-Fi and publishes temperature and humidity over MQTT.
Payloads and topics follow the [messaging contract](../../docs/05-backend/04-messaging-contract.md), so the backend ingests them like any other node.

| File | Job |
|---|---|
| `main/main.c` | Sampling loop, RAM buffer, telemetry JSON, MQTT client, `status` online/offline (last will) |
| `main/dht11.c` | DHT11 single-wire driver (bit-banged, interrupts off for the 5 ms transfer) |
| `main/wifi.c` | Wi-Fi station, reconnects on its own |
| `main/Kconfig.projbuild` | Settings shown in `menuconfig` under "SmartHive node" |
| `main/certs/` | Device certificates, git-ignored, see its README |

What it sends, every `SMARTHIVE_SAMPLE_INTERVAL_S` seconds:

- `smarthive/v1/nodes/<node_id>/telemetry`, QoS 1: `temp_in` (degC) and `rh_in` (pct_rh) from sensor `dht11-0`. A failed read is sent as `value: null, quality: read_error`.
- `smarthive/v1/nodes/<node_id>/status`, retained: `online` after connecting, `offline` as last will.

While the broker is unreachable, up to 120 samples wait in RAM and go out in batches of 8 when it is back. Time comes from NTP; until the first sync `clock_synced` is `false`.

## Wiring

| DHT11 | ESP32 |
|---|---|
| VCC | 3V3 |
| DATA | GPIO 4 (configurable), 10 kΩ pull-up to 3V3 if the module has none |
| GND | GND |

## Build and flash

Needs ESP-IDF 5.3 or newer. On 6.x the MQTT client comes from the component registry; `main/idf_component.yml` pulls it.

```bash
cd edge/esp32
# certificates first (main/certs/README.md), or turn TLS off in menuconfig for a plain test broker
idf.py set-target esp32
idf.py menuconfig          # SmartHive node: Wi-Fi SSID/password, node id, broker URI, GPIO, interval
idf.py build flash monitor
```

With PlatformIO: `pio run -t menuconfig`, then `pio run -t upload -t monitor`.

The broker URI is the address of the machine running the Compose stack, for example `mqtts://192.168.1.50:8883`. The broker certificate must list that address; reissue it with `BROKER_SAN="DNS:localhost,DNS:mosquitto,IP:192.168.1.50" ./gen_certs.sh ...` after deleting `broker.crt`/`broker.key` (or, in a lab only, enable "Do not check the broker certificate name").

Status: builds with ESP-IDF 6.1 (PlatformIO `espressif32`) and the payload builder was checked against the backend's `Telemetry` model; not yet tried on hardware.
