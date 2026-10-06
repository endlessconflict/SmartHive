# ADR-0004: MQTT as the integration contract, images over HTTPS

Status: Proposed
Date: 2026-10-06
Deciders: Karen Jimenez, James Tack, Ricardo Villarreal

## Context

The node, the simulator, the backend and the dashboard are built in parallel. The node's link is Ethernet today and may be LoRaWAN or cellular later. Connections drop, the node reboots without a clock, and data must not be lost (US03, NFR-06). REQ-11 already specifies MQTT with TLS.

## Decision

- Node-to-server messages (telemetry, events, summaries, health, status) and server-to-node messages (config, commands) use MQTT 3.1.1/5 over TLS with Mosquitto, on topics `smarthive/v1/nodes/{node_id}/...`, QoS 1 except health.
- Payloads are versioned JSON validated against JSON Schemas kept in `infra/contracts/`, which are the single source of truth.
- Every message carries a UUIDv7 `msg_id`; the server deduplicates on it.
- Images are uploaded over HTTPS to the API, referenced from MQTT events by `image_id`.
- The node uses a SQLite outbox and marks data sent only after PUBACK.

Details: [messaging contract](../05-backend/04-messaging-contract.md).

## Alternatives considered

| Option | Why not |
|---|---|
| HTTP only (node POSTs everything) | No server-to-node channel without polling, no last will for offline detection, more overhead per message |
| Images over MQTT | Large payloads block the broker and the node's queue; impossible over LoRaWAN anyway |
| CoAP | Less tooling, less familiar to the team |
| Protobuf or CBOR now | Harder to debug. JSON is fine on Ethernet; the structure is kept CBOR-ready for later |

## Consequences

- Duplicates are expected and handled; the ingestor must be idempotent.
- The simulator can stand in for any number of nodes.
- A LoRaWAN path later means a bridge from ChirpStack into the same topics, not a new backend.
