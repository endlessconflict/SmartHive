# Backend

Status: Proposed

Owner: James Tack. Messaging contract: Karen Jimenez. Deployment: Maria de los Angeles Agudelo.

## Summary

The node does the image work and sends small messages. A Mosquitto broker on the gateway receives them over MQTT with TLS. An ingestor validates each message against a versioned schema and stores it in PostgreSQL with the TimescaleDB extension, ignoring duplicates. A FastAPI service exposes the data to the dashboard over REST and WebSocket and accepts image uploads from the node. A worker evaluates rules, manages alerts and sends notifications. Everything server-side is one Python package deployed as a few containers with Docker Compose, on whatever machine acts as the gateway.

The same MQTT contract is spoken by the real node and by the hive simulator, so the backend can be developed, tested and demoed without hardware.

## Reading order

| # | Document | Content |
|---|---|---|
| 1 | [Architecture overview](01-architecture-overview.md) | Constraints, components, flows, why a modular monolith |
| 2 | [Tech stack](02-tech-stack.md) | Every tool and its license |
| 3 | [Edge node software](03-edge-node-software.md) | Services on the Pi, store-and-forward, time, storage |
| 4 | [Messaging contract](04-messaging-contract.md) | Topics, payloads, QoS, image upload, versioning |
| 5 | [Data model](05-data-model.md) | Tables and why |
| 6 | [API design](06-api-design.md) | REST and WebSocket endpoints |
| 7 | [Alerts and rules](07-alerts-and-rules.md) | Catalog, lifecycle, channels |
| 8 | [Deployment and operations](08-deployment-and-operations.md) | Compose, environments, security, backups, CI |

## Decisions

| ADR | Decision |
|---|---|
| [0003](../adr/0003-raspberry-pi-3b-edge-node.md) | Raspberry Pi 3B as the edge node for Prototype 1 |
| [0004](../adr/0004-mqtt-as-integration-contract.md) | MQTT as the integration contract, transport-agnostic |
| [0005](../adr/0005-postgresql-timescaledb-apache.md) | PostgreSQL + TimescaleDB (Apache-2.0 features only) |
| [0006](../adr/0006-python-modular-monolith.md) | Python modular monolith with FastAPI |
| [0007](../adr/0007-filesystem-image-storage.md) | Images on the filesystem, metadata in the database |
