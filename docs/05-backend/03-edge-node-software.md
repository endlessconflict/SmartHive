# Edge node software

Status: Proposed

Owners: Ricardo Villarreal (sensors, OS, agent), Adrien Cubilla (vision), Karen Jimenez (uplink)

Code: `edge/` (planned)

## Services

Small services instead of one big program, so a crash or memory spike in vision cannot stop the sensors. They share one SQLite database (the outbox) and a config file.

| Service | Does | Writes | Reads | Memory limit |
|---|---|---|---|---|
| `sensord` | Reads DHT11 every `sample_interval` (later HX711, battery monitor) | `readings` | config | 60 MB |
| `camd` | Captures low-res stream for motion, full-res stills on motion; night mode | frames in tmpfs | config | 120 MB |
| `visiond` | Two-stage detection, aggregation, keeps relevant images | `detections`, `events`, `images`, image files | frames | 250 MB |
| `uplinkd` | Publishes outbox rows over MQTT, uploads images over HTTPS, handles acks and backoff | sent flags | everything pending | 60 MB |
| `agentd` | Applies config from the server, runs commands, publishes health and heartbeat, watches the clock | `health`, config file | MQTT `cmd`, `config` | 40 MB |

All are Python, packaged together as `smarthive_edge`, each started by its own systemd unit with `Restart=always` and `MemoryMax=`.

## The outbox

Store-and-forward is what makes US03 and FR-13 true. Everything the node wants to send goes into SQLite first, and leaves only when the server has confirmed it.

```sql
CREATE TABLE outbox (
  msg_id       TEXT PRIMARY KEY,      -- UUIDv7: unique and time-ordered
  kind         TEXT NOT NULL,         -- telemetry | event | health | detection_summary
  topic        TEXT NOT NULL,
  payload      BLOB NOT NULL,         -- JSON, already serialized
  created_at   INTEGER NOT NULL,      -- unix ms, node clock
  clock_synced INTEGER NOT NULL,      -- 0/1
  priority     INTEGER NOT NULL,      -- 0 = events first, 1 = telemetry, 2 = health
  attempts     INTEGER NOT NULL DEFAULT 0,
  sent_at      INTEGER                -- NULL until PUBACK received
);
CREATE INDEX outbox_pending ON outbox (sent_at, priority, created_at);

CREATE TABLE images (
  image_id     TEXT PRIMARY KEY,      -- UUIDv7, also referenced by events
  path         TEXT NOT NULL,
  sha256       TEXT NOT NULL,
  bytes        INTEGER NOT NULL,
  captured_at  INTEGER NOT NULL,
  reason       TEXT NOT NULL,         -- threat | varroa | periodic
  uploaded_at  INTEGER
);
```

Settings: `PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;`. Writers batch inserts (for example every 10 s or 50 rows) to limit SD card writes.

### Uplink algorithm

```text
loop:
  ensure MQTT session (TLS, persistent session, last will on status topic)
  rows = pending rows ordered by priority, then created_at, limit 100
  group telemetry rows into one batch message (max ~16 KB)
  publish each message with QoS 1
  on PUBACK: mark rows sent
  on failure: exponential backoff (1 s → 5 min, with jitter)
  upload pending images (oldest threat images first), one at a time, resumable
  every hour: delete sent rows older than retention; delete uploaded images older than retention
```

Events are sent before telemetry, so after an outage the first thing the server learns is that a hornet was seen, not the 300 temperature readings that piled up. Within a priority, oldest first.

If storage runs low, the node drops in this order: periodic images, then old frame summaries, then the oldest telemetry. Every drop is counted and reported in health messages, so the gap is visible on the server.

## Configuration

One YAML file, `/etc/smarthive/node.yaml`, with defaults shipped in the package. The server can override fields by publishing a retained message on the node's `config` topic; `agentd` validates it, writes it, and asks the relevant service to reload.

```yaml
node_id: node-0001
hive_id: null                      # assigned on the server; informational here
server:
  mqtt: mqtts://gateway.local:8883
  api: https://gateway.local
  ca_file: /etc/smarthive/ca.crt
sampling:
  dht11_interval_s: 60
  weight_interval_s: 300
camera:
  motion_fps: 2
  night_mode: {enabled: true, from: "18:45", to: "06:00"}   # or computed from coordinates
vision:
  stage1_model: yolo11n-320-int8@1.0.0
  stage2_model: mnv3s-128-int8@1.0.0
  thresholds: {hornet: 0.45, shb: 0.50, other_insect: 0.50, bee: 0.35, varroa: 0.60}
  aggregation: {hornet: {k: 3, n: 10}, shb: {k: 2, n: 10}}
  keep_periodic_image_every_min: 60
storage:
  outbox_retention_days: 7
  image_retention_days: 3          # after upload
```

## Health and heartbeat

`agentd` publishes on the `health` topic every 60 s (and `status: online` as a retained message on connect):

| Field | Source |
|---|---|
| `uptime_s` | `/proc/uptime` |
| `soc_temp_c` | `/sys/class/thermal/thermal_zone0/temp` |
| `throttled` | `vcgencmd get_throttled` decoded (under-voltage, frequency capped, throttled, now and since boot) |
| `cpu_load`, `mem_used_mb` | `/proc` |
| `disk_free_mb` | `statvfs` |
| `outbox_pending`, `images_pending`, `dropped_total` | Outbox |
| `clock_synced`, `ntp_offset_ms` | chrony |
| `battery_v`, `battery_ma` | When an INA219 is fitted |
| `versions` | Software and model versions |

## Time

The Pi has no real-time clock ([review notes](../02-hardware/hardware-review-notes.md#4-no-real-time-clock)).

- chrony on the node syncs to the gateway's chrony. Until it reports sync, readings carry `clock_synced = false`.
- Each record also stores the monotonic clock (`CLOCK_BOOTTIME`) and a boot ID. When sync happens, `agentd` records the offset between monotonic and wall time for that boot; the ingestor can then correct unsynced records from the same boot exactly.
- An RTC module would make this mostly unnecessary.

## Storage budget

On the 32 GB card, with about 4 GB used by the OS:

| Data | Rate | Retention on the node | Space |
|---|---|---|---|
| Telemetry | ~4,300 readings/day at 1 per minute × 3 channels, ~200 B each | 7 days after sending | < 10 MB |
| Frame summaries | Up to ~10,000/day on a busy entrance, ~1 KB each | 7 days | < 100 MB |
| Kept images | 50 to 300 relevant + 12 periodic per day, ~400 to 600 KB each | 3 days after upload; up to the outbox retention if offline | 0.2 to 1.3 GB |
| Logs (persisted warnings only) | Small | journald limits | < 200 MB |

Total worst case: a few GB, well within NFR-05. Even two weeks offline fits.

## Development without hardware

Every hardware access sits behind a small interface (`TemperatureHumiditySensor`, `Camera`, `PowerMonitor`) with a real implementation and a fake one. The fakes read from the telemetry simulator's output and from synthetic image sequences. The whole node software runs on a laptop with `SMARTHIVE_HARDWARE=fake`, against the Docker Compose stack, which is how it is tested in CI.

## Provisioning

1. Flash Raspberry Pi OS Lite 64-bit, enable SSH with a key.
2. Run the Ansible playbook from `edge/provision/`: packages, the `smarthive` user, `config.txt` overlays (`dtoverlay=dht11,gpiopin=4`, camera, `gpu_mem`), chrony, journald volatile, systemd units, the device certificate.
3. Register the node on the server (`node_id`, credentials) and assign it to a hive in the dashboard.

## OTA (REQ-14)

Planned, not designed. The minimum for Prototype 1 is the Ansible playbook run over SSH from the gateway, plus model packages pushed with `rsync` and versioned so rollback is one command. A proper pull-based update with signature checks is in the [roadmap](../roadmap.md).
