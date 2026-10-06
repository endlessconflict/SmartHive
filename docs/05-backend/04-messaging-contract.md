# Messaging contract

Status: Proposed. Becomes "Accepted" when Karen, James, Ricardo and Adrien have all signed off; after that, changes follow the versioning rules below.

Owner: Karen Jimenez. Image upload endpoint: James Tack.

Machine-readable source of truth: JSON Schemas in `infra/contracts/` (planned). This page explains them. If the two disagree, the schemas win and this page gets fixed.

## Principles

- Topics identify the **node**, not the hive. A node can be moved to another hive; the server keeps the assignment history. This avoids rewriting topics and ACLs when someone moves a box.
- Every message has a globally unique `msg_id` (UUIDv7, which also sorts by time). The server deduplicates on it, which makes QoS 1 safe.
- Every reading has its own timestamp, taken when it was measured, not when it was sent. Batches can be hours old.
- Payloads are JSON in Prototype 1. The structure is kept flat and small so it can be mapped to CBOR for a constrained link later without changing meaning.
- Units are fixed per quantity. No unit conversion happens on the server.

## Topics

Prefix: `smarthive/v1/nodes/{node_id}/`

| Topic suffix | Direction | QoS | Retained | Content |
|---|---|---|---|---|
| `telemetry` | node → server | 1 | no | Batch of sensor readings |
| `events` | node → server | 1 | no | Detection events and node-side alarms |
| `summary` | node → server | 1 | no | Vision summary every 10 min: counts, Varroa index window |
| `health` | node → server | 0 | no | Health snapshot every 60 s |
| `status` | node → server | 1 | yes | `online` on connect; `offline` as last will |
| `config` | server → node | 1 | yes | Desired configuration (partial overrides) |
| `cmd` | server → node | 1 | no | Commands |
| `cmd/ack` | node → server | 1 | no | Command results |

Broker ACLs (Mosquitto pattern syntax), so a node can only touch its own topics:

```text
pattern write smarthive/v1/nodes/%u/telemetry
pattern write smarthive/v1/nodes/%u/events
pattern write smarthive/v1/nodes/%u/summary
pattern write smarthive/v1/nodes/%u/health
pattern write smarthive/v1/nodes/%u/status
pattern write smarthive/v1/nodes/%u/cmd/ack
pattern read  smarthive/v1/nodes/%u/config
pattern read  smarthive/v1/nodes/%u/cmd
```

The MQTT username of each device is its `node_id`. The backend services and the simulator have their own accounts with wider rights. The simulator's fake nodes use `node_id`s with a `sim-` prefix, so synthetic data can never be mistaken for real data in the database.

## Common envelope

Every node-to-server payload starts with:

```json
{
  "schema": "smarthive.telemetry/1.0",
  "msg_id": "0190f5a2-7c1e-7d43-9a1b-2f6c8e0d4b11",
  "node_id": "node-0001",
  "boot_id": "6c1f0b0e-...",
  "sent_at": "2026-10-06T14:05:00.000Z"
}
```

## telemetry

```json
{
  "schema": "smarthive.telemetry/1.0",
  "msg_id": "0190f5a2-...",
  "node_id": "node-0001",
  "boot_id": "6c1f0b0e-...",
  "sent_at": "2026-10-06T14:05:00.000Z",
  "readings": [
    {"ts": "2026-10-06T14:04:00.120Z", "mono_ms": 8712345, "clock_synced": true,
     "sensor": "dht11-0", "quantity": "temp_in", "value": 35, "unit": "degC", "quality": "ok"},
    {"ts": "2026-10-06T14:04:00.120Z", "mono_ms": 8712345, "clock_synced": true,
     "sensor": "dht11-0", "quantity": "rh_in", "value": 58, "unit": "pct_rh", "quality": "ok"},
    {"ts": "2026-10-06T14:05:00.118Z", "mono_ms": 8772343, "clock_synced": true,
     "sensor": "dht11-0", "quantity": "temp_in", "value": null, "unit": "degC", "quality": "read_error"}
  ]
}
```

| Quantity | Unit | Sensor in Prototype 1 |
|---|---|---|
| `temp_in` | `degC` | DHT11 |
| `rh_in` | `pct_rh` | DHT11 |
| `temp_out` | `degC` | Optional |
| `rh_out` | `pct_rh` | Optional |
| `weight` | `kg` | Future HX711 |
| `battery_v` | `V` | Future INA219 |
| `battery_i` | `mA` | Future INA219 |

Quality codes: `ok`, `read_error`, `clipped`, `stuck`, `clock_unsynced`. Adding a quantity is a minor version change; the server stores unknown quantities rather than rejecting them, so a new sensor on the node does not break ingestion.

Each reading's identity on the server is `(msg_id, index in batch)`, so a duplicated batch is dropped as a whole.

## events

```json
{
  "schema": "smarthive.event/1.0",
  "msg_id": "0190f5a3-...",
  "node_id": "node-0001",
  "boot_id": "6c1f0b0e-...",
  "sent_at": "2026-10-06T14:03:30.000Z",
  "event": {
    "type": "threat_detected",
    "episode_id": "0190f5a2-6a00-7c10-8e2b-1d2f3a4b5c6d",
    "cls": "hornet",
    "first_seen": "2026-10-06T14:03:02.004Z",
    "last_seen": "2026-10-06T14:03:21.412Z",
    "clock_synced": true,
    "max_conf": 0.81,
    "frames_positive": 4,
    "frames_window": 10,
    "image_id": "0190f5a2-7c1e-7d43-9a1b-2f6c8e0d4b12",
    "models": {"stage1": "yolo11n-320-int8@1.0.0", "stage2": "mnv3s-128-int8@1.0.0"}
  }
}
```

Event types in v1:

| Type | Raised when |
|---|---|
| `threat_detected` | A threat class passes the k-of-n rule. One event per episode; repeated sightings within 10 min update `last_seen` in a new message with the same `episode_id` |
| `varroa_high` | The rolling Varroa index crosses the configured threshold with enough bees counted |
| `sensor_fault` | A sensor fails repeatedly or reports stuck values |
| `storage_low` | Free space below a threshold |
| `dropped_data` | The node had to discard unsent data |

## summary

Every 10 minutes, so the server can show traffic and the Varroa index without receiving every frame:

```json
{
  "schema": "smarthive.summary/1.0",
  "msg_id": "...", "node_id": "node-0001", "boot_id": "...", "sent_at": "...",
  "window": {"start": "2026-10-06T14:00:00Z", "end": "2026-10-06T14:10:00Z", "clock_synced": true},
  "frames_analyzed": 312,
  "counts": {"bee": 2950, "hornet": 4, "shb": 0, "other_insect": 37},
  "varroa": {"bees_classified": 1840, "positive": 41},
  "latency_ms_p95": {"stage1": 610, "total": 1450}
}
```

## health and status

`health` fields are listed in [edge node software](03-edge-node-software.md#health-and-heartbeat). It uses QoS 0 because a lost health message is replaced by the next one a minute later.

`status` is retained. The node sets its last will to `{"state": "offline"}` on connect and publishes `{"state": "online", "boot_id": "..."}` right after connecting. On a clean shutdown it publishes `{"state": "offline", "reason": "shutdown"}` itself.

## config and cmd

`config` is retained so a node that reconnects gets its desired configuration immediately:

```json
{"schema": "smarthive.config/1.0", "config_version": 7,
 "set": {"sampling": {"dht11_interval_s": 30}, "vision": {"thresholds": {"hornet": 0.4}}}}
```

The node acknowledges by including `config_version` in its next health message.

`cmd`:

```json
{"schema": "smarthive.cmd/1.0", "cmd_id": "0190f5b0-...", "name": "capture_now", "args": {}, "expires_at": "2026-10-06T14:20:00Z"}
```

| Command | Effect |
|---|---|
| `capture_now` | Take and upload a full image (for the dashboard's "refresh" button) |
| `reboot` | Restart the node |
| `sync_time` | Force an NTP sync |
| `upload_logs` | Upload the last N hours of service logs |
| `ping` | Reply immediately (latency check) |

`cmd/ack`: `{"cmd_id": "...", "result": "ok" | "error" | "expired", "detail": "..."}`. Commands past `expires_at` are not executed.

## Image upload

Images go over HTTPS, not MQTT.

```http
POST /device/v1/images HTTP/1.1
Host: gateway.local
Authorization: Bearer <device token>
Content-Type: multipart/form-data; boundary=...

--...
Content-Disposition: form-data; name="meta"
Content-Type: application/json

{"image_id": "0190f5a2-...-4b12", "node_id": "node-0001", "captured_at": "2026-10-06T14:03:21.412Z",
 "clock_synced": true, "reason": "threat", "sha256": "9f2c...", "width": 1640, "height": 1232,
 "objects": [{"cls": "hornet", "conf": 0.76, "box": [90, 40, 260, 170]}]}
--...
Content-Disposition: form-data; name="file"; filename="0190f5a2-...-4b12.jpg"
Content-Type: image/jpeg

<bytes>
--...--
```

| Response | Meaning | Node does |
|---|---|---|
| `201 Created` | Stored | Mark uploaded |
| `200 OK` | Already have this `image_id` with the same hash | Mark uploaded |
| `409 Conflict` | Same `image_id`, different hash | Log error, keep file, alert in health |
| `413`, `415`, `422` | Rejected | Log error, do not retry |
| `5xx`, timeout | Server problem | Retry with backoff |

Device tokens are long random strings issued at registration and stored on the node with file permissions `600`. Mutual TLS with the device certificate is an alternative if Caddy is configured for it.

## Versioning

- The topic carries the major version (`v1`). A breaking change creates `v2` topics; the server listens to both during a transition.
- The `schema` field carries `major.minor`. Minor versions only add optional fields. Consumers ignore fields they do not know.
- A schema change is a pull request to `infra/contracts/` approved by the owners of both sides (see [team and roles](../00-project/team-and-roles.md#contract-owners)).

## Contract tests

| Test | Where it runs |
|---|---|
| Every example in this page validates against its schema | CI, `infra/contracts/` |
| Node fixtures (captured from the node code) validate | CI, `edge/` |
| Simulator replay output validates | CI, `simulation/` |
| Ingestor accepts every valid fixture and rejects a set of invalid ones | CI, `backend/` |
| Duplicate batch inserted twice produces one set of rows | CI, `backend/` integration test with Testcontainers |

## Ready for a constrained link

LoRaWAN payloads are tens to a couple of hundred bytes. If a LoRaWAN sensor node is added later:

- Telemetry readings map to a compact CBOR array (`[quantity_code, value_scaled_int, quality_code, ts_offset_s]`), a few bytes each.
- Events map to a fixed short structure; images are never sent over the radio.
- A bridge from ChirpStack's MQTT integration decodes them and republishes on the `v1` topics above, so nothing downstream changes.
