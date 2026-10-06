# ADR-0006: Python modular monolith with FastAPI

Status: Proposed
Date: 2026-10-06
Deciders: James Tack, Maria de los Angeles Agudelo

## Context

The server needs an MQTT ingestor, an HTTP/WebSocket API, a rules and notification worker, and scheduled jobs, including ML jobs written by the AI members of the team. The team has one backend developer. Everyone writes Python.

## Decision

One Python package, `smarthive`, with three entry points (`ingest`, `api`, `worker`) built into one Docker image and run as three containers. FastAPI for HTTP and WebSocket, SQLAlchemy 2 and Alembic for the database, Pydantic models generated from the message schemas and shared by all three. PostgreSQL `LISTEN/NOTIFY` for events between them; no separate message queue.

## Alternatives considered

| Option | Why not |
|---|---|
| Microservices in several languages | Operational and integration cost far above what one semester and one backend developer can carry |
| Node.js or Go backend | Splits the codebase from the AI and simulation code, which is Python |
| Django | Heavier, and its strengths (admin, templates) matter less here than async MQTT and WebSocket handling |
| Redis/Valkey or RabbitMQ between processes | Another service to run; `LISTEN/NOTIFY` and MQTT cover our needs |

## Consequences

- One test suite, one image, shared contracts.
- Module boundaries (`ingest`, `api`, `worker`, `notify`, `db`, `contracts`) must be respected in code review so the monolith can be split later if needed.
