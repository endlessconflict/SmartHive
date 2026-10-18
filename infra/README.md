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

## Generating certificates (pki/)

The broker only accepts clients that present a certificate signed by the local CA, and the MQTT user is the certificate's CN. So the CN has to be the node id (`node-0001`) or the service name (`backend`).

```bash
cd infra/pki
./gen_certs.sh backend node-0001     # first run: CA, broker certificate, and these two clients
./gen_certs.sh node-0002             # later runs only add the new client; the CA and earlier certificates stay valid
```

Generated files are git-ignored. Never commit `.key` or `.crt` files. The broker certificate is valid for `localhost`, `mosquitto`, `gateway.local` and `127.0.0.1`; set `BROKER_SAN` if the gateway has another name.

## Who may publish where (mosquitto/acl)

The rules follow the [messaging contract](../docs/05-backend/04-messaging-contract.md#topics): a node writes only its own `smarthive/v1/nodes/<node-id>/...` topics and reads only its own `config` and `cmd`; `backend` reads every node topic and writes `config` and `cmd`. The test that proves it, against a real broker, is `backend/tests/integration/test_broker_contract.py`. Change the ACL together with that test.

Owners: Maria de los Angeles Agudelo (stack), Karen Jimenez (broker and contracts), James Tack (backend services).