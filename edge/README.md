# edge/

Software that runs on the Raspberry Pi 3B node.

Status: Planned, except the vision runtime. Design is in [docs/05-backend/03-edge-node-software.md](../docs/05-backend/03-edge-node-software.md).

The detection logic `visiond` will run already exists and is tested in the [SmartHive-Vision](https://github.com/endlessconflict/SmartHive-Vision) repository (`smarthive_vision.pipeline`, ncnn only, no torch). The node installs the release pinned in [`vision.lock`](../vision.lock); `python scripts/fetch_vision.py --install` downloads, verifies and installs it. The other dependencies for the Pi are pinned in [`requirements.txt`](requirements.txt).

| Service | Job | Owner |
|---|---|---|
| `sensord` | Read DHT11 (later HX711 and others) on a schedule, write readings to the outbox | Ricardo |
| `camd` | Capture frames, run the motion gate, hand candidate frames to `visiond` | Ricardo, Adrien |
| `visiond` | Two-stage pest detector (NCNN), write detections and relevant images | Adrien |
| `uplinkd` | Drain the outbox over MQTT/TLS, upload images over HTTPS | Karen |
| `agentd` | Configuration, remote commands, health and heartbeat | Ricardo |

## DHT11 telemetry (first prototype)

| Folder | What |
|---|---|
| [`esp32/`](esp32/README.md) | ESP32 firmware in C (ESP-IDF): DHT11, Wi-Fi, MQTT over mutual TLS |
| [`raspberry/`](raspberry/README.md) | The same node in Python for the Raspberry Pi (DHT11 through the kernel IIO driver) |
| [`scripts/`](scripts/README.md) | `fake_telemetry.py`: fake `sim-` nodes with Gaussian noise to test the backend |

All three publish `temp_in` and `rh_in` on `smarthive/v1/nodes/<node_id>/telemetry` following the messaging contract. The `sensord` and `uplinkd` services below will replace the Raspberry Pi version.

Planned layout:

```text
edge/
├── smarthive_edge/        Python package shared by all services
│   ├── outbox.py          SQLite store-and-forward
│   ├── sensors/           DHT11 (kernel IIO), HX711, mocks
│   ├── camera/            picamera2 / V4L2 capture, motion gate
│   ├── vision/            Model loading and inference
│   └── uplink/            MQTT client, image uploader
├── systemd/               Unit files with memory limits
├── config/                Default node configuration (YAML)
└── tests/                 Run on any Linux machine with mocked hardware
```

Constraints to remember: 1 GB of RAM, no Docker, no PyTorch, no real-time clock, microSD storage.
