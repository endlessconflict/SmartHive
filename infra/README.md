# infra/

Everything needed to run the server side: Docker Compose, broker configuration, certificates tooling and the message contracts.

Status: Planned. Design is in [docs/05-backend/08-deployment-and-operations.md](../docs/05-backend/08-deployment-and-operations.md).

```text
infra/
├── compose.yaml          Services; profiles `dev` and `field`
├── .env.example          Every variable a service needs, with dummy values
├── mosquitto/            mosquitto.conf, ACL file template
├── postgres/             Init scripts (TimescaleDB extension)
├── caddy/                Reverse proxy config
├── pki/                  Scripts to create the local CA and device certificates (no keys in git)
└── contracts/            JSON Schemas for every MQTT payload, the single source of truth
```

Owners: Maria de los Angeles Agudelo (stack), Karen Jimenez (broker and contracts), James Tack (backend services).
