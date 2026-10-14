# infra/

Everything needed to run the server side: Docker Compose, broker configuration, certificates tooling and the message contracts.

Status: Stack v1 works (Sprint 4): Mosquitto with TLS, PostgreSQL with TimescaleDB (Apache-2.0 build), the API and Mailpit start healthy. Caddy, ingest, worker, chrony and the dashboard come with their stories. Design is in [docs/05-backend/08-deployment-and-operations.md](../docs/05-backend/08-deployment-and-operations.md).

```text
infra/
├── compose.yaml          Services; profile `dev` adds Mailpit
├── .env.example          Every variable a service needs, with dummy values
├── mosquitto/            mosquitto.conf, acl, users.sh (password file), test_broker.sh (US04 check)
├── pki/                  make-ca.sh: local CA and broker certificate (output in pki/out, git-ignored)
└── contracts/            JSON Schemas for every MQTT payload, the single source of truth
```

## Start the stack

```bash
cp infra/.env.example infra/.env                 # set the two passwords
bash infra/pki/make-ca.sh                        # once: CA and broker certificate
bash infra/mosquitto/users.sh healthcheck <pw>   # same password as MQTT_HEALTHCHECK_PASSWORD
bash infra/mosquitto/users.sh backend             # prints a random password once
bash infra/mosquitto/users.sh node-0001           # one per device; username is the node_id
docker compose -f infra/compose.yaml --profile dev up -d
```

The API answers on `http://localhost:8000/readyz`, Mailpit on `http://localhost:8025`, the broker on `8883` (TLS only; nothing listens on 1883).

Check US04 against the running broker:

```bash
MQTT_BACKEND_PASSWORD=<pw> MQTT_NODE1_PASSWORD=<pw> bash infra/mosquitto/test_broker.sh
```

## Contracts

```bash
python -m pytest infra/contracts          # schemas, valid and invalid examples
bash infra/contracts/generate-models.sh   # regenerate backend/src/smarthive/contracts
```

Owners: Maria de los Angeles Agudelo (stack), Karen Jimenez (broker and contracts), James Tack (backend services).
