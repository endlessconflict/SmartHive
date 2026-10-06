# SmartHive documentation

This folder holds everything we know and have decided about the project. It is organized by area, with numbered folders so they sort in reading order. Each file covers one topic.

If you are new, read in this order: [overview](00-project/overview.md), [requirements](01-requirements/objectives-and-requirements.md), [hardware review notes](02-hardware/hardware-review-notes.md), [data strategy](04-data/01-data-problem-and-strategy.md), [backend architecture](05-backend/01-architecture-overview.md), [roadmap](roadmap.md).

## Status legend

Every document starts with a status line:

| Status | Meaning |
|---|---|
| Draft | Written, not yet reviewed by the team |
| Proposed | Reviewed by its author's area, waiting for team agreement |
| Accepted | Agreed. Changes need a PR and, if big, an ADR |
| Planned | Only an outline. The work is scheduled in the roadmap but not done |

## Map

### 00 Project

| Document | What it covers |
|---|---|
| [overview.md](00-project/overview.md) | Problem, users, expected impact, scope and out of scope |
| [team-and-roles.md](00-project/team-and-roles.md) | Who owns what, Scrum roles, contract owners |
| [way-of-working.md](00-project/way-of-working.md) | Sprints, ceremonies, board, definition of done |
| [risks.md](00-project/risks.md) | Risk register with mitigations, updated after the data decision |
| [glossary.md](00-project/glossary.md) | Beekeeping and technical terms used across the docs |

### 01 Requirements

| Document | What it covers |
|---|---|
| [objectives-and-requirements.md](01-requirements/objectives-and-requirements.md) | General and specific objectives, functional and non-functional requirements of the node |
| [epics-and-user-stories.md](01-requirements/epics-and-user-stories.md) | Four epics, features and user stories US01 to US22, with traceability |
| [elicitation-matrix.md](01-requirements/elicitation-matrix.md) | The 30 questions for the client, still open, and what each one blocks |
| [backlog.md](01-requirements/backlog.md) | Product backlog items from the team spreadsheet |

### 02 Hardware

| Document | What it covers |
|---|---|
| [node-functional-architecture.md](02-hardware/node-functional-architecture.md) | Subsystems, blocks and physical allocation |
| [electrical-design-prototype-1.md](02-hardware/electrical-design-prototype-1.md) | Schematic and component choices for Prototype 1 |
| [power-budget.md](02-hardware/power-budget.md) | Estimated consumption and battery autonomy |
| [hardware-review-notes.md](02-hardware/hardware-review-notes.md) | Issues found while designing the software on top of this hardware |

### 03 Vision

| Document | What it covers |
|---|---|
| [README.md](03-vision/README.md) | Summary and reading order |
| [01-problem-framing.md](03-vision/01-problem-framing.md) | Classes, scale of the problem, what "detected" means |
| [02-camera-and-optics.md](03-vision/02-camera-and-optics.md) | Resolution math: why Varroa drives every camera decision |
| [03-synthetic-image-pipeline.md](03-vision/03-synthetic-image-pipeline.md) | How we generate labeled entrance images |
| [04-model-architecture.md](03-vision/04-model-architecture.md) | Two-stage detector for a Raspberry Pi 3B |
| [05-training-and-evaluation.md](03-vision/05-training-and-evaluation.md) | Splits, metrics, sim-to-real evaluation, acceptance criteria |
| [06-edge-deployment.md](03-vision/06-edge-deployment.md) | Runtime pipeline on the node |

### 04 Data

| Document | What it covers |
|---|---|
| [README.md](04-data/README.md) | Summary and reading order |
| [01-data-problem-and-strategy.md](04-data/01-data-problem-and-strategy.md) | Why synthetic, the four data tiers, rules that keep us honest |
| [02-hive-telemetry-simulator.md](04-data/02-hive-telemetry-simulator.md) | Model of temperature, humidity and weight of a hive |
| [03-scenarios-and-events.md](04-data/03-scenarios-and-events.md) | Swarming, absconding, harvests, sensor faults and how they are injected |
| [04-sensor-and-node-realism.md](04-data/04-sensor-and-node-realism.md) | DHT11, HX711, power gaps, clock drift, duplicates |
| [05-dataset-versioning-and-governance.md](04-data/05-dataset-versioning-and-governance.md) | DVC, dataset cards, licenses, seeds |

### 05 Backend

| Document | What it covers |
|---|---|
| [README.md](05-backend/README.md) | Summary and reading order |
| [01-architecture-overview.md](05-backend/01-architecture-overview.md) | Constraints, components, data flows |
| [02-tech-stack.md](05-backend/02-tech-stack.md) | Languages, frameworks and tools, with licenses |
| [03-edge-node-software.md](05-backend/03-edge-node-software.md) | Services on the Raspberry Pi and store-and-forward |
| [04-messaging-contract.md](05-backend/04-messaging-contract.md) | MQTT topics, payloads, QoS, image upload |
| [05-data-model.md](05-backend/05-data-model.md) | Database schema |
| [06-api-design.md](05-backend/06-api-design.md) | REST and WebSocket API |
| [07-alerts-and-rules.md](05-backend/07-alerts-and-rules.md) | Alert catalog, lifecycle, notification channels |
| [08-deployment-and-operations.md](05-backend/08-deployment-and-operations.md) | Docker Compose, environments, security, backups |

### Cross-cutting

| Document | What it covers |
|---|---|
| [roadmap.md](roadmap.md) | Phased plan for all areas, including work not designed yet |
| [adr/](adr/README.md) | Architecture decision records |
| [references.md](references.md) | Papers, datasets and tools cited in these docs |

## Where the source material came from

These docs consolidate the team's working documents from the first sprints: the project plan presentation, the design document ("Diseño"), the epics and user stories document, the elicitation matrix, the pest detection proposal and the backlog spreadsheet. Spanish sources were translated. Where the sources disagree (for example ESP32 + LoRaWAN in the presentation versus Raspberry Pi 3B + Ethernet in the electrical design), the docs say so and point to the decision that resolves it.
