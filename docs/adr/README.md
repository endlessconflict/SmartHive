# Architecture decision records

An ADR records one decision that would be expensive to reverse: what we decided, why, and what it costs us. They are short on purpose. Once accepted, an ADR is not edited; a later ADR supersedes it.

Process: copy [0000-template.md](0000-template.md), take the next number, open a PR. The ADR is accepted when the PR is merged after review by the owners of the areas it affects.

| ADR | Title | Status | Date |
|---|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted | 2026-10-06 |
| [0002](0002-synthetic-first-training-data.md) | Synthetic-first training data | Accepted | 2026-10-06 |
| [0003](0003-raspberry-pi-3b-edge-node.md) | Raspberry Pi 3B as the Prototype 1 edge node | Proposed | 2026-10-06 |
| [0004](0004-mqtt-as-integration-contract.md) | MQTT as the integration contract, images over HTTPS | Proposed | 2026-10-06 |
| [0005](0005-postgresql-timescaledb-apache.md) | PostgreSQL with TimescaleDB, Apache-2.0 features only | Proposed | 2026-10-06 |
| [0006](0006-python-modular-monolith.md) | Python modular monolith with FastAPI | Proposed | 2026-10-06 |
| [0007](0007-filesystem-image-storage.md) | Images on the filesystem, metadata in the database | Proposed | 2026-10-06 |
| [0008](https://github.com/endlessconflict/SmartHive-Vision/blob/main/docs/adr/0008-detector-licensing.md) | Detector framework and repository license | Accepted | 2026-10-06 |
| [0009](https://github.com/endlessconflict/SmartHive-Vision/blob/main/docs/adr/0009-procedural-insect-rendering.md) | Procedural insect rendering instead of photo cutouts | Accepted | 2026-10-06 |
| [0010](https://github.com/endlessconflict/SmartHive-Vision/blob/main/docs/adr/0010-real-photos-with-automatic-labels.md) | Real photos with automatic labels before 3D rendering or diffusion | Accepted | 2026-10-06 |
| [0011](https://github.com/endlessconflict/SmartHive-Vision/blob/main/docs/adr/0011-osi-clean-automatic-labeling.md) | Automatic labeling with OSI-licensed weights only | Accepted | 2026-10-07 |
