# Backend handoff

Status: Accepted

Where the backend stands and what the next person needs to know. The plan is in [Backend plan](09-backend-plan.md).

## State

Stories BE1 to BE5 and the image upload are merged to `main`. BE6 to BE9 are open as pull requests #13 to #16 and wait for review. BE10 has not started.

#13, #14 and #15 each branch from `main` and each add a router to `smarthive/api/app.py`. Merge them in order and run `git merge origin/main` into the next branch each time; the conflict is the router list and is trivial. #16 is stacked on #15, so retarget it to `main` after #15 merges.

## Layout

```
backend/src/smarthive/
  api/          FastAPI app, auth, routes, live.py (WebSocket hub)
  alerts/       rules, engine, store, delivery (email, ntfy)
  contracts/    pydantic models for MQTT payloads
  db/           schema access, migrations
  ingest/       MQTT subscriber and topic handlers
  jobs.py       helpers for the ML jobs
  maintenance.py  purge, backup, restore check
  weather.py    Open-Meteo fetch
  cli.py        smarthive migrate | create-user | api | worker | backup | restore-check
```

Commands run from `backend/` with `./.venv/Scripts/python` on Windows. Docker must be running for the integration tests.

## Things that bit us

- **Test database reset.** `tests/integration/conftest.py` truncates with `CASCADE`, which wipes `alert_rules`. The fixture snapshots the rules on the first test and re-inserts them after each truncate.
- **asyncpg parameter types.** asyncpg infers a parameter type from its first use. Timestamps passed to SQL are cast with `CAST(:now AS timestamptz)`.
- **Mosquitto in CI.** The container user could not read the PKI temp directory on the Linux runner. The contract test sets mode 755 on the directory and 644 on the files.
- **Python version.** CI uses 3.11. Do not use newer syntax.
- **Backup in Docker.** The image installs `postgresql-client-16` from PGDG. The base image is Debian trixie, so the codename comes from `/etc/os-release`. In CI the round-trip test skips unless the PG tools are present.

## Assumptions to confirm

- `throttled.under_voltage` as the key for the power-low rule. Confirm with the node software owner.
- The anomalies and predictions table contract in [Data model](05-data-model.md), "Who writes what". Confirm with Diego.
- The simulator needs one certificate per node to pass the ACLs (EN-02).
- `leohatvani` in CODEOWNERS is assumed to be Adrien. SCRUM-31 is assigned to Adrien and stays open.
