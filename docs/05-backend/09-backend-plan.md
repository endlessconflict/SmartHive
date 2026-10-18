# Backend plan

Status: Accepted

Owner: James Tack. This is the plan behind epic SCRUM-81 ("E05 Backend Platform") in Jira. Each story below maps to one pull request.

## Order of work

The stories follow the data. The broker has to accept messages before the ingestor can store them, and the API can only show what is stored.

| Story | Jira | Sprint | Scope | Pull request |
|---|---|---|---|---|
| BE1 | SCRUM-82 | S4 | Broker with mutual TLS, per-node ACLs, contract test against a real Mosquitto | #3 |
| BE2 | SCRUM-83 | S4 | Ingest every topic, node registry, `NOTIFY` on new rows | #4 |
| BE3 | SCRUM-84 | S4 | FastAPI app, login with refresh rotation, `/me`, apiaries, health, Dockerfile | #5 |
| BE4 | SCRUM-85, 62 | S5 | Hives and nodes API, device tokens, node-to-hive assignment with back-fill | #6, #9 |
| BE5 | SCRUM-86, 51, 52 | S5 | Alert engine, node offline and power alerts, email and ntfy delivery | #6, #7, #8 |
| (image) | SCRUM-66 | S5 | Image upload and gallery | #10 |
| BE6 | SCRUM-87 | S6 | Live updates over WebSocket | #13 |
| BE7 | SCRUM-88 | S6 | Beekeeper log, anomalies, predictions | #14 |
| BE8 | SCRUM-89, 75 | S7 | CSV and JSONL export, weather overlay | #15 |
| BE9 | SCRUM-90 | S8 | Retention purge, backup, restore check | #16 |
| BE10 | SCRUM-91 | S8 | 48 hour soak with five simulated hives | not started |

## Rules for every pull request

- Branch from `main` (or from the branch it depends on), one story per branch.
- `ruff format`, `ruff check`, `mypy` and `pytest` pass before each commit. CI runs the same four.
- Integration tests use real PostgreSQL/TimescaleDB and a real Mosquitto in Docker. No mocks for the broker or the database.
- Migrations are forward-only Alembic files, one per story that needs schema changes.
- Docs change in the same pull request as the behaviour they describe.

## What is left

- **BE10 (SCRUM-91).** The soak needs a demo machine and the hive simulator running for 48 hours. It cannot be done on a development laptop.
- **Image thumbnails** (`?w=` on the file route) and the **email template with a thumbnail**. The sender works; the message is plain text.
- **Missing alert rules.** [Alerts and rules](07-alerts-and-rules.md) lists them under "Implementation status".
- **Restore run on the real stack.** The round trip passes with `pg_dump` shims. It still needs one run against the Compose stack, and the runbook checked against it.
- **Open questions for other owners:** the shape of `throttled.under_voltage` in health snapshots (node software), the table contract for anomalies and predictions (Diego), and per-node certificates for the simulator (EN-02).
