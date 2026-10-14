# backend/

Server-side services: MQTT ingestor, REST/WebSocket API, rules and alerts, scheduled jobs.

Status: Skeleton. `smarthive.api.main` serves `/healthz` and `/readyz`, Alembic has the baseline migration of the data model, and `smarthive.contracts` holds the models generated from `infra/contracts`. Ingest and worker are not written yet. Design is in [docs/05-backend/](../docs/05-backend/README.md).

One Python package (`smarthive`) with several entry points, deployed as separate containers from the same image:

| Entry point | Job |
|---|---|
| `smarthive ingest` | Subscribe to MQTT, validate payloads, store telemetry and detections idempotently |
| `smarthive api` | FastAPI app: REST, WebSocket live feed, image upload from nodes, exports |
| `smarthive worker` | Rules, alert lifecycle, notifications, node-offline detection, ML job scheduling |

Planned layout:

```text
backend/
├── src/smarthive/
│   ├── contracts/        Pydantic models generated from the JSON Schemas in infra/contracts
│   ├── db/               SQLAlchemy models, Alembic migrations
│   ├── ingest/
│   ├── api/
│   ├── worker/
│   └── notify/           Email, in-app, ntfy
└── tests/
```

Owner: James Tack.
