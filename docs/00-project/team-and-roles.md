# Team and roles

Status: Accepted

## Technical roles

| Member | Area | Responsibilities | Main folders |
|---|---|---|---|
| James Tack | Backend and data | Data ingestion, time-series database, REST API | `backend/`, `infra/` (shared) |
| Ricardo Villarreal | Embedded systems | Sensor node, load cell, sensors, power management, OTA | `edge/` (hardware side), `docs/02-hardware/` |
| Adrien Cubilla | AI: signals and vision | Pest detection model, swarm acoustic classifier | [SmartHive-Vision](https://github.com/endlessconflict/SmartHive-Vision) |
| Diego Alejandro Vasquez | AI: time series | Honey yield prediction, anomaly detection | `ml/`, `simulation/` (telemetry) |
| Karen Jimenez | Communications | Gateway, LoRaWAN/NB-IoT study, MQTT over TLS, message format | `infra/mosquitto/`, messaging contract |
| Maria de los Angeles Agudelo | Frontend and DevOps | Dashboard, alert system UI, integration, Docker, deployment | `frontend/`, `infra/`, CI |

## Scrum roles

- Scrum Master: Diego Alejandro Vasquez
- Product Owner: Adrien Cubilla

## Contract owners

Most integration failures happen at the boundaries between areas. Each contract has an owner who must approve changes, and a consumer who must be told.

| Contract | Document | Owner | Main consumers |
|---|---|---|---|
| MQTT topics and payloads | [messaging contract](../05-backend/04-messaging-contract.md) | Karen | Ricardo (node), James (ingestor), Diego and Adrien (simulator) |
| Image upload API | [messaging contract](../05-backend/04-messaging-contract.md#image-upload) | James | Ricardo, Adrien |
| Database schema | [data model](../05-backend/05-data-model.md) | James | Diego (ML jobs), Maria (via API) |
| Public REST/WebSocket API | [API design](../05-backend/06-api-design.md) | James | Maria |
| Detection output format | [model architecture](https://github.com/endlessconflict/SmartHive-Vision/blob/main/docs/04-model-architecture.md#output-contract) | Adrien | Ricardo, James |
| Synthetic dataset formats | [dataset governance](../04-data/05-dataset-versioning-and-governance.md) | Adrien (images), Diego (telemetry) | Everyone who trains or tests |
| Electrical pinout | [electrical design](../02-hardware/electrical-design-prototype-1.md) | Ricardo | Everyone touching the node |

## Shared ownership

Some components do not belong to a single area:

- The hive simulator (`simulation/telemetry`) is co-owned by Diego (signal models) and James (MQTT replay), because both the ML and backend work depend on it.
- The Docker Compose stack (`infra/`) is owned by Maria, with James responsible for the backend services inside it.
- The node software (`edge/`) is split: Ricardo owns sensors, power and the OS image; Adrien owns the vision service; Karen owns the uplink.
