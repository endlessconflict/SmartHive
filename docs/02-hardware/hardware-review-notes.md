# Hardware review notes

Status: Proposed. For discussion with Ricardo at the next planning meeting.

These notes came up while designing the software, data and backend on top of the Prototype 1 hardware. None of them blocks the prototype. Some change what the software has to do, and a few deserve a decision.

## 1. Two different node designs are in circulation

The project plan presentation and the first backlog story describe an **ESP32** node with a load cell, microphone and camera, talking **LoRaWAN/MQTT** to the cloud. The design document and electrical schematic describe a **Raspberry Pi 3B** node with a DHT11 and a camera, connected by **Ethernet** to a local gateway.

Both are reasonable, for different goals. The ESP32 is what you want for battery life and long-range radio. The Pi is what you need to run an image detector on the node (FR-05, US11): an ESP32 can run very small models, but not a bee detector followed by a Varroa classifier on cropped high-resolution patches.

Proposed resolution, written up in [ADR-0003](../adr/0003-raspberry-pi-3b-edge-node.md):

- Prototype 1 is the Raspberry Pi 3B design. Everything in this repository targets it.
- The MQTT contract is written so that a future ESP32 sensor node (weight, temperature, humidity, maybe audio features) can publish to the same topics, through a LoRaWAN network server if needed. Nothing in the backend assumes the sender is a Pi.
- The presentation and backlog should be updated so they stop contradicting the design.

## 2. The Raspberry Pi 3B has 1 GB of RAM, and no other option

The component table says "define memory: 1 GB, 2 GB or 4 GB in relation to compute requirements". The Pi 3 Model B (and 3B+) only exists with 1 GB of LPDDR2. Memory options start with the Pi 4.

Consequences for the software:

- No Docker on the node. Services run as plain systemd units with Python virtual environments.
- No PyTorch on the node. Models are exported to NCNN or ONNX and run with a small runtime.
- Each service gets a memory limit (`MemoryMax=` in systemd), so the vision service cannot starve the sensor service.
- The detector input is 320 to 416 px, not 640 px. See [model architecture](https://github.com/endlessconflict/SmartHive-Vision/blob/main/docs/04-model-architecture.md).

If a Pi 4 (2 GB or more) becomes available at no cost, the same software runs on it unchanged and roughly twice as fast. Nothing should depend on that.

## 3. The DHT11 limits what the data can show

| Property | DHT11 | Why it matters here |
|---|---|---|
| Temperature range | 0 to 50 °C | Fine for inside a hive |
| Temperature accuracy / resolution | ±2 °C / 1 °C | The brood nest is regulated within about 1 °C. Subtle loss of thermoregulation is below this sensor's resolution |
| Humidity range | 20 to 90 % RH | Tropical outdoor air and a hive during a strong nectar flow can exceed 90 % |
| Humidity accuracy / resolution | ±5 % RH / 1 % | Good for trends, poor for absolute values |
| Sampling rate | About 1 reading per second at most | Not a constraint at 1 reading per minute |
| Protocol | Single-wire, timing-critical | Unreliable from user-space Python on Linux; use the kernel driver |

What we do about it:

- The [telemetry simulator](../04-data/04-sensor-and-node-realism.md) reproduces these limits (integer output, clipping, ±2 °C bias per sensor, occasional failed reads). Models trained on synthetic data then learn from the precision we will actually have, not from perfect curves.
- The node reads the sensor with the Linux kernel's IIO driver (`dtoverlay=dht11,gpiopin=4` in `config.txt`, values under `/sys/bus/iio/devices/`). It handles the timing in the kernel and retries on checksum errors.
- If a better sensor is available for free (SHT31, SHT4x, BME280, all I²C), the software will support it from the start. The schema stores the sensor model with each reading.

## 4. No real-time clock

The Pi has no battery-backed clock. After a power loss it boots with the time it last saved to disk (`fake-hwclock`), which can be hours or days off, until it reaches an NTP server. Readings taken in that window get wrong timestamps, and store-and-forward will faithfully deliver them later.

What we do about it:

- The gateway runs an NTP server (chrony) and the node syncs to it on boot.
- Every reading carries `clock_synced: true|false`. The ingestor can correct unsynced readings using the monotonic clock offset once sync happens, or flag them.
- Recommendation: a DS3231 RTC module on I²C fixes this properly for very little effort.

## 5. "Power alert" cannot be implemented without measuring the battery

US06 asks to warn when a hive stops sending data "so that I can check whether the device has run out of power or lost its connection". Without a voltage reading, both cases look identical from the server: messages stop.

What we can do without hardware changes: detect silence (MQTT last will + heartbeat timeout), and report the Pi's under-voltage flag while it still runs. To actually tell the two apart, the node needs a voltage/current sensor on the battery line (INA219, or an ADS1115 with a divider). Then the last messages before silence show the voltage dropping, and the backend can say "probably battery".

## 6. Autonomy is about one day

See the [power budget](power-budget.md). The Pi 3B cannot sleep. With the battery alone, the node lasts roughly half a day to one day. The autonomy requirement has to be set with this in mind.

## 7. Heat

The node will sit outdoors in a tropical climate. The Pi 3B starts throttling its CPU at about 80 °C. In a closed enclosure in the sun, with the detector running, that is reachable.

- The detector's duty cycle is low thanks to motion gating, which helps.
- Health messages report SoC temperature and throttling, so the problem is visible.
- The DHT11 must not sit next to the Pi. Heat from the board would bias it. It belongs inside the hive, on a cable.

## 8. microSD wear and corruption

Flash cards die from constant small writes and get corrupted by sudden power loss. Both are likely here.

- SQLite in WAL mode with batched commits, not one transaction per reading.
- System logs in RAM (`Storage=volatile` in journald, or log2ram), with only warnings and errors persisted.
- Images written once and never rewritten.
- Stretch goal: read-only root filesystem with a separate data partition.
- Keep a card image of a working setup, so recovery takes minutes.

## 9. Camera requirements

The camera is still "to be defined". Varroa decides the requirements: a 1.1 mm by 1.6 mm mite has to cover enough pixels to be recognizable. The [camera and optics document](https://github.com/endlessconflict/SmartHive-Vision/blob/main/docs/02-camera-and-optics.md) works out the numbers. The short version: at least about 8 pixels per millimeter on the landing board, a focus distance that matches the mounting, and a CSI camera if possible because it takes less CPU than USB.

## 10. Load cell is in the stories, not in the schematic

US02 (weight) is priority 1, and weight is the most useful single signal for swarming, robbing, absconding and yield. Prototype 1 has no HX711. Until it does, weight exists only in the simulator. The software treats weight as just another `quantity`, so adding it later requires no backend change.
