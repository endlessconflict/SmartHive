# API design

Status: Proposed

Owner: James Tack. Main consumer: Maria de los Angeles Agudelo (dashboard).

FastAPI generates the OpenAPI document at `/api/v1/openapi.json`; the dashboard generates its TypeScript client from it. This page is the design intent; the generated document is the reference once code exists.

## Conventions

- Base path `/api/v1` for users, `/device/v1` for nodes.
- JSON everywhere, `snake_case` fields, timestamps in ISO 8601 UTC.
- Lists are paginated with `limit` and an opaque `cursor`.
- Errors use RFC 9457 problem details: `{"type", "title", "status", "detail"}`.
- Time ranges are `from` and `to` (half-open), with `bucket` for downsampling.
- Every response that contains simulated data says so (`"simulated": true` on the hive or node).

## Authentication

| Client | Method |
|---|---|
| Dashboard users | `POST /api/v1/auth/login` with email and password → short-lived access token (15 min) and a refresh token in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie. `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout` |
| Nodes | `Authorization: Bearer <device token>` on `/device/v1/*`, token hash stored in `nodes` |
| WebSocket | Access token sent in the first message after connecting, not in the URL |

Authorization: a `beekeeper` sees apiaries they own; an `admin` sees everything and manages nodes and users (EL-01 working assumption).

## Endpoints

### Apiaries, hives, nodes

| Method and path | Purpose | Story |
|---|---|---|
| `GET /apiaries`, `POST /apiaries`, `PATCH /apiaries/{id}` | Manage apiaries | EL-02 |
| `GET /hives?apiary_id=` | List hives with status summary (last reading, open alerts, node status) | Main screen, EL-21 |
| `POST /hives`, `GET /hives/{id}`, `PATCH /hives/{id}` | Hive details and metadata | EL-03 |
| `GET /nodes`, `POST /nodes` (admin) | Register a node, returns the device token once | |
| `POST /nodes/{id}/assign` `{hive_id, from}` | Assign a node to a hive | |
| `GET /nodes/{id}/health?from=&to=` | Health history | Ops |
| `POST /nodes/{id}/commands` `{name, args}` | Send a command (for example `capture_now`) | US15 |

### Telemetry

| Method and path | Purpose | Story |
|---|---|---|
| `GET /hives/{id}/latest` | Last value of each quantity, with age and quality | US01, main screen |
| `GET /hives/{id}/readings?quantity=temp_in&quantity=rh_in&from=&to=&bucket=15m&agg=avg` | History for charts. `bucket` from `1m` to `1d`; `agg` one of `avg`, `min`, `max`, `last`. Gaps are returned as gaps, never interpolated | US13 |
| `GET /hives/{id}/weather?from=&to=` | Site weather for overlays | US20 |

Example response for `readings`:

```json
{
  "hive_id": "8d0c...",
  "simulated": false,
  "bucket": "15m",
  "series": [
    {
      "quantity": "temp_in", "unit": "degC",
      "points": [["2026-10-06T14:00:00Z", 34.8], ["2026-10-06T14:15:00Z", 35.0], ["2026-10-06T14:30:00Z", null]]
    }
  ]
}
```

### Vision

| Method and path | Purpose | Story |
|---|---|---|
| `GET /hives/{id}/images/latest` | Most recent image with its detected objects | US15 |
| `GET /hives/{id}/images?reason=threat&from=&to=` | Image gallery | |
| `GET /images/{id}` | Metadata; `GET /images/{id}/file` returns the JPEG (supports `?w=` thumbnails) | |
| `GET /hives/{id}/detections?from=&to=&cls=` | Detection events | US09, US10 |
| `GET /hives/{id}/varroa?from=&to=&bucket=1d` | Varroa index over time, with counts and confidence interval | US09 |
| `GET /hives/{id}/traffic?from=&to=&bucket=1h` | Bee counts from summaries | |

### Alerts

| Method and path | Purpose | Story |
|---|---|---|
| `GET /alerts?state=open&hive_id=&severity=` | Alert list | US12, US17 |
| `GET /alerts/{id}` | Alert with its event log | US14 |
| `POST /alerts/{id}/acknowledge` | Mark as seen | US14, EL-20 |
| `POST /alerts/{id}/resolve` `{note}` | Mark as handled, with what the beekeeper did | US14 |
| `GET /alert-rules`, `PATCH /alert-rules/{id}` | View and adjust predefined thresholds | EL-19 |
| `GET /me/notifications`, `POST /me/notifications/{id}/read` | In-app notification inbox | US12 |
| `PATCH /me` | Notification preferences (email on/off, ntfy topic) | EL-18 |

### Beekeeper log

| Method and path | Purpose |
|---|---|
| `GET /hives/{id}/management-events`, `POST ...` | Log inspections, supers, harvests, feeding, treatments. Used to mask disturbances and as yield ground truth |

### Predictions and anomalies (Epic 3.3 and 4)

| Method and path | Purpose | Story |
|---|---|---|
| `GET /hives/{id}/anomalies?from=&to=` | Anomaly windows with scores | US16, US17 |
| `GET /hives/{id}/predictions?target=yield_7d_kg` | Latest prediction as a range (p10, p50, p90) | US18, US19 |

### Export

| Method and path | Purpose | Story |
|---|---|---|
| `GET /exports/readings?hive_id=&quantity=&from=&to=&format=csv` | Streamed CSV or JSON Lines; filters for hive, variables and range | REQ-09, EL-24 |
| `GET /exports/detections?...` | Same for detection events | |

Exports include the `quality` and `clock_synced` columns, and a header comment with the hive, the node, and whether the data is simulated.

### Device endpoints

| Method and path | Purpose |
|---|---|
| `POST /device/v1/images` | Image upload, described in the [messaging contract](04-messaging-contract.md#image-upload) |
| `GET /device/v1/time` | Server time, as a last resort when NTP is blocked |

## WebSocket: live updates

`GET /api/v1/ws` (upgraded). After authenticating, the client subscribes to hives:

```json
{"op": "auth", "token": "..."}
{"op": "subscribe", "hives": ["8d0c...", "1a2b..."]}
```

The server pushes:

```json
{"type": "reading", "hive_id": "8d0c...", "quantity": "temp_in", "ts": "...", "value": 35, "quality": "ok"}
{"type": "detection", "hive_id": "8d0c...", "cls": "hornet", "first_seen": "...", "image_id": "..."}
{"type": "alert", "alert_id": "...", "state": "open", "severity": "critical", "title": "Hornet at the entrance"}
{"type": "node_status", "node_id": "node-0001", "status": "offline"}
```

The source is PostgreSQL `LISTEN/NOTIFY`: the ingestor and the worker notify after committing, and the API process forwards to subscribed sockets. Late-arriving backlog data is not pushed as "live"; the dashboard refetches the chart range when it sees a `backfill` message for a hive.

## Health and metrics

| Path | Purpose |
|---|---|
| `GET /healthz` | Liveness |
| `GET /readyz` | Database and broker reachable |
| `GET /metrics` | Prometheus format (optional) |
