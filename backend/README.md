# backend/

Server-side services: MQTT ingestor, REST/WebSocket API, rules and alerts, scheduled jobs.

Status: the telemetry ingestor exists (SCRUM-10, US05). It subscribes to `smarthive/v1/nodes/+/telemetry`, validates each batch and stores it in PostgreSQL/TimescaleDB exactly once. The API, the worker and the other topics (`events`, `summary`, `health`, `status`) are not written yet. Design is in [docs/05-backend/](../docs/05-backend/README.md).

One Python package (`smarthive`) with several entry points, deployed as separate containers from the same image:

| Entry point | Job | State |
|---|---|---|
| `smarthive ingest` | Subscribe to MQTT, validate payloads, store telemetry idempotently | Telemetry only |
| `smarthive api` | FastAPI app: REST, WebSocket live feed, image upload from nodes, exports | Planned |
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
│   ├── contracts/telemetry.py   Pydantic model of the telemetry message (hand-written until infra/contracts exists)
│   ├── db/migrations/        Alembic (async); 0001_baseline is the data model
│   └── ingest/
│       ├── handler.py        validate() and insert(): no MQTT, easy to test
│       └── service.py        MQTT loop: persistent session, manual ack, reconnect, SIGTERM
└── tests/{unit,integration,fixtures}
```

## How a batch is handled

1. The payload is rejected as a whole, never partly stored, if any rule fails: UTF-8 JSON object of at most 256 KiB; `schema` is `smarthive.telemetry/1.x`; `msg_id` is a UUID; `node_id` equals the one in the topic; every reading has a timezone-aware `ts`, a known `quality`, a finite `value` (null only for `read_error`) and, for a known quantity, its contract unit. Unknown fields are ignored and unknown quantities are stored.
2. A rejected message is logged as one WARNING (`event=telemetry_rejected`) and acknowledged, so the broker does not redeliver it. The service keeps running.
3. A valid batch is inserted in one transaction with `ON CONFLICT DO NOTHING` on `(msg_id, idx, ts)`. `hive_id` comes from `node_assignments` at the time of the reading, and is NULL when the node is not assigned. `mono_ms`, `boot_id` and `unit` are validated but not stored.
4. The PUBACK is sent after the commit (manual acknowledgement), the session is persistent, and a database or broker outage is retried with backoff instead of dropping the batch.

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

## Tests

```bash
pytest tests/unit                 # no Docker
pytest                            # everything; the integration tests start TimescaleDB and Mosquitto with Testcontainers
                                  # (needs Docker, bash and openssl: test_broker_contract.py issues certificates with infra/pki/gen_certs.sh)
ruff check . && ruff format --check . && mypy
```

On Windows, aiomqtt needs a selector event loop; the CLI and the tests set it up.

Owner: James Tack.
