# backend/

Server-side services: MQTT ingestor, REST/WebSocket API, rules and alerts, scheduled jobs.

Status: the ingestor handles all five node topics (`telemetry`, `events`, `summary`, `health`, `status`; SCRUM-10 and SCRUM-83). It validates each message and stores it in PostgreSQL/TimescaleDB exactly once, registers nodes on first contact and sends a NOTIFY after each commit. The API and the worker are not written yet. Design is in [docs/05-backend/](../docs/05-backend/README.md).

One Python package (`smarthive`) with several entry points, deployed as separate containers from the same image:

| Entry point | Job | State |
|---|---|---|
| `smarthive ingest` | Subscribe to MQTT, validate payloads, store every node topic idempotently | Done |
| `smarthive api` | FastAPI app: REST, WebSocket live feed, image upload from nodes, exports | Login, refresh, logout, `/me`, apiaries list, health checks |
| `smarthive migrate` | Apply the database migrations (what the Compose stack runs before the other services) | Done |
| `smarthive create-user` | Create the first administrator without SQL; the password is prompted for or read from stdin | Done |
| `smarthive seed` | Publish fake node messages (telemetry, health, summary, events, status) to the broker; see [Test data](#test-data) | Done |
| `smarthive worker` | Rules, alert lifecycle, notifications, node-offline detection, ML job scheduling | Planned |

## Layout

```text
backend/
├── pyproject.toml            Python >= 3.11, src layout, script: smarthive = smarthive.cli:main
├── .env.example              Dummy values for every SMARTHIVE_* setting
├── alembic.ini
├── src/smarthive/
│   ├── cli.py                `smarthive ingest`, JSON logs on stdout
│   ├── config.py             Settings from SMARTHIVE_* environment variables
│   ├── contracts/            Pydantic models of the messaging contract: common (envelope), telemetry, event,
│   │                         summary, health, status. Hand-written until infra/contracts exists
│   ├── db/migrations/        Alembic (async); 0001 is the data model, 0002 the node registry
│   └── ingest/
│       ├── base.py           Handler, Stored, Result, Rejected
│       ├── handlers/         One module per topic suffix: parse() and store(); __init__ lists them
│       ├── handler.py        validate() and ingest(): topic -> handler, one transaction, NOTIFY. No MQTT
│       └── service.py        MQTT loop: persistent session, manual ack, reconnect, SIGTERM
└── tests/{unit,integration,fixtures}
```

To support a new message type, write `ingest/handlers/<name>.py` with `parse` and `store`, add its `HANDLER` to `handlers/__init__.py`, and add a fixture and a test. The MQTT loop subscribes to every registered topic by itself.

## How a message is handled

1. The payload is rejected as a whole, never partly stored, if any rule fails: UTF-8 JSON object of at most 256 KiB; the topic is `smarthive/v1/nodes/{node_id}/{kind}` for a known `kind`; the `schema` is `smarthive.<kind>/1.x`; `msg_id` is a UUID; `node_id` equals the one in the topic (the `status` payload has no envelope, so the topic alone is the identity); and the fields of that kind are valid (for telemetry: aware `ts`, known `quality`, finite `value`, contract unit). Unknown fields are ignored, unknown quantities and event types are stored.
2. A rejected message is logged as one WARNING (`event=message_rejected`, with the reason) and acknowledged, so the broker does not redeliver it. The service keeps running.
3. A valid message runs in one transaction: the node is registered or touched, the handler stores its rows with `ON CONFLICT DO NOTHING`, and a `pg_notify` on the `smarthive_ingest` channel is queued. The notification goes out only if the transaction commits, and only if something new was stored.
4. The PUBACK is sent after the commit (manual acknowledgement), the session is persistent, and a database or broker outage is retried with backoff instead of dropping the message.

What each topic stores:

| Topic | Table | Identity (dedup) | Notes |
|---|---|---|---|
| `telemetry` | `readings` | `(msg_id, idx, ts)` | `hive_id` from `node_assignments` at the reading time, NULL if unassigned |
| `events` | `detection_events` | `msg_id` | A repeated sighting is a new message with the same `episode_id`. An event without an episode is its own episode |
| `summary` | `vision_summaries` | `msg_id` and `(node_id, window_start)` | A window counts once even if re-sent under a new id |
| `health` | `node_health` | `(node_id, ts)` | Stored as received. With `clock_synced: false` the arrival time replaces `sent_at` |
| `status` | `nodes.status` | the state itself | The retained message is redelivered on every reconnect; setting the same state again changes nothing |

Nodes register themselves: `simulated` follows the id prefix `sim-`, never the payload. `last_seen_at` moves on every accepted message. Only `health` sets a node online (it is QoS 0, so it is never a queued leftover); a `status` message is applied as is; telemetry, events and summaries only update `last_seen_at`.

## Run it locally

Needs Docker, Python 3.11+ and, for the demo, the TimescaleDB `-oss` image (Apache-2.0 features only, ADR-0005) and Mosquitto. There is no Compose file yet; plain `docker run` is enough.

```bash
docker run -d --name sh-pg -p 5432:5432 -e POSTGRES_USER=smarthive -e POSTGRES_PASSWORD=smarthive \
  -e POSTGRES_DB=smarthive timescale/timescaledb:2.17.2-pg16-oss
docker run -d --name sh-mqtt -p 1883:1883 eclipse-mosquitto:2.0.22 mosquitto -c /mosquitto-no-auth.conf

cd backend
pip install -e ".[dev]"
cp .env.example .env              # defaults already point at localhost
alembic upgrade head
smarthive ingest                  # JSON logs; Ctrl+C finishes the batch in flight, then exits
```

The broker above has no TLS and no authentication: it is for a laptop only. The broker in `infra/` requires mutual TLS: set `SMARTHIVE_MQTT_PORT=8883`, `SMARTHIVE_MQTT_TLS_CA`, `SMARTHIVE_MQTT_TLS_CERT` and `SMARTHIVE_MQTT_TLS_KEY` to the files from `infra/pki/gen_certs.sh backend`. The MQTT user is the certificate's CN, so no username or password is needed.

Demo, from another terminal: publish the fixture twice, then count.

```bash
mosquitto_pub -h localhost -t smarthive/v1/nodes/node-0001/telemetry -q 1 -f tests/fixtures/telemetry_valid.json
mosquitto_pub -h localhost -t smarthive/v1/nodes/node-0001/telemetry -q 1 -f tests/fixtures/telemetry_valid.json
docker exec sh-pg psql -U smarthive -c \
  "SELECT count(*) FROM readings WHERE msg_id = '0190f5a2-7c1e-7d43-9a1b-2f6c8e0d4b11'"
# 3, not 6
```

This ran on a synthetic fixture modelled on the messaging contract, not on hardware or the simulator. The second batch logs `inserted: 0, duplicates: 3`.

## Docker image

One image runs every process; the command picks which.

```bash
docker build -t smarthive-backend backend
docker run --rm --env-file backend/.env smarthive-backend migrate
echo "a-long-password" | docker run --rm -i --env-file backend/.env smarthive-backend create-user --email you@example.com --name "You" --password-stdin
docker run -d -p 8000:8000 --env-file backend/.env smarthive-backend api --host 0.0.0.0     # then GET /api/v1/docs
docker run -d --env-file backend/.env smarthive-backend ingest
```

It runs as a non-root user (uid 10001). `SMARTHIVE_JWT_SECRET` is mandatory for `api`; there is no default.

## Test data

`smarthive seed` plays the part of an edge node, so a fresh stack can be filled without hardware. It builds each message from the contract (`docs/05-backend/04-messaging-contract.md`) and publishes it with QoS 1 on `smarthive/v1/nodes/<node>/<kind>`.

```bash
# Needs the node's own client certificate: the broker takes the MQTT user from the CN and
# only lets a node write to its own topics (the `backend` certificate cannot publish node data).
cd infra/pki && ./gen_certs.sh node-0001
export SMARTHIVE_MQTT_PORT=8883 SMARTHIVE_MQTT_TLS_CA=infra/pki/ca.crt        SMARTHIVE_MQTT_TLS_CERT=infra/pki/node-0001.crt SMARTHIVE_MQTT_TLS_KEY=infra/pki/node-0001.key
smarthive seed --scenario hornet --rounds 5 --interval 10 --seed 42
```

| Scenario | What it sends | What it should cause |
|---|---|---|
| `normal` | Telemetry (3 readings per quantity, 5 min apart), health, summary | Rows in `readings`, `node_health`, summaries; node registered |
| `hornet` | `normal` plus one `threat_detected` hornet event per round | A `hornet` alert |
| `varroa` | `normal` with about 22 % varroa-positive bees | A `varroa_high` alert |
| `low-battery` | `battery_v` near 9.8 V and `under_voltage` set | A `node_power_low` alert |
| `offline` | A retained `status: offline` message | A `node_offline` alert |

`--node` picks the node id (it must match the certificate CN), `--rounds` and `--interval` repeat the batch, and `--seed` makes the values repeatable. Readings are backdated so the time-window rules can fire on the first round. Every payload is validated against the contract models in `tests/unit/test_seeder.py`, and `tests/integration/test_seeder.py` pushes them through the ingest path into TimescaleDB. To see alerts, the `worker` service has to be running and the node assigned to a hive.

## Tests

```bash
pytest tests/unit                 # no Docker
pytest                            # everything; the integration tests start TimescaleDB and Mosquitto with Testcontainers
                                  # (needs Docker, bash and openssl: test_broker_contract.py issues certificates with infra/pki/gen_certs.sh)
ruff check . && ruff format --check . && mypy
```

On Windows, aiomqtt needs a selector event loop; the CLI and the tests set it up.

Owner: James Tack.
