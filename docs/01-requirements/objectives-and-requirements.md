# Objectives and requirements of the node

Status: Accepted (translated and renumbered from the design document "Diseño")

The original document numbered every functional requirement as `RF-1`. They are renumbered here as `FR-01` to `FR-13` and `NFR-01` to `NFR-08` so they can be referenced individually. The wording is a translation; the meaning has not changed. Notes in the last column are new.

## General objective

Develop an autonomous monitoring node for beekeeping that acquires environmental variables and images in an apiary, processes information locally, stores the data and transmits the measurements, using a battery-based energy architecture suited to adverse environmental conditions.

## Specific objectives

| ID | Objective |
|---|---|
| OBJ-1 | Acquire environmental variables relevant to apiary monitoring, in particular temperature and humidity |
| OBJ-2 | Acquire images of the area of interest in the apiary, to provide visual information usable for pest detection |
| OBJ-3 | Process images locally on the node, reducing the need to send full images to external systems |
| OBJ-4 | Store the measurements and generated data locally, keeping a history of the node's observations |
| OBJ-5 | Transmit the measurements to an external system for later query, analysis or supervision |
| OBJ-6 | Operate autonomously on batteries, within the energy limits of a remotely installed device |
| OBJ-7 | Keep operating under adverse conditions, in particular humidity and potentially corrosive agents in the apiary |

## Functional requirements

| ID | The node shall... | Traces to | Notes |
|---|---|---|---|
| FR-01 | measure the temperature of the apiary environment | OBJ-1, US01 | "Environment" should be read as inside the hive (brood nest). See EL-03 |
| FR-02 | measure the humidity of the apiary environment | OBJ-1, US01 | DHT11 range is 20 to 90 % RH; see [hardware notes](../02-hardware/hardware-review-notes.md) |
| FR-03 | acquire images with a camera installed on the node | OBJ-2, US07 | Camera model still to be defined |
| FR-04 | allow the acquired images to be used for pest detection | OBJ-2, US09, US10 | |
| FR-05 | process images locally, without relying on an external system for the main processing | OBJ-3, US11 | Drives the choice of a Linux-class board |
| FR-06 | store the measurements locally during operation | OBJ-4, US03 | |
| FR-07 | transmit the measurements to an external system | OBJ-5, US05 | |
| FR-08 | acquire environmental variables periodically, at a configurable sampling interval | OBJ-1 | Default interval pending EL-05 |
| FR-09 | acquire images at a configurable frequency | OBJ-2 | Default pending EL-06 |
| FR-10 | run from a battery-based power supply | OBJ-6 | |
| FR-11 | keep operating for a minimum period, to be defined | OBJ-6 | **Autonomy not defined yet.** [Power budget](../02-hardware/power-budget.md) estimates about one day with the current design |
| FR-12 | log the state of its acquisition, storage and transmission processes, to make supervision easier | OBJ-4, US06 | Becomes the `health` MQTT topic |
| FR-13 | keep storing measurements locally when transmission is unavailable, avoiding immediate data loss | OBJ-4, US03 | Store-and-forward outbox |

## Non-functional requirements

| ID | Requirement | Notes |
|---|---|---|
| NFR-01 | The node shall operate autonomously on batteries for the established period | Period not defined |
| NFR-02 | Power consumption shall be compatible with the required autonomy | Consumption not defined; estimate in the power budget |
| NFR-03 | The device shall operate in the environmental conditions of the installation site, including humidity | Tropical site: high ambient humidity and heat |
| NFR-04 | External materials shall resist prolonged exposure to humidity and potentially corrosive agents | Enclosure design is open work |
| NFR-05 | Storage capacity shall be enough for the data generated during the established period | 32 GB card; see estimate in [edge node software](../05-backend/03-edge-node-software.md#storage-budget) |
| NFR-06 | Temporary loss of communication shall not cause the loss of measurements already stored locally | |
| NFR-07 | The device shall protect internal electronics from the environmental conditions of the site | |
| NFR-08 | The node shall operate stably during the established period, minimizing lost measurements and failures in acquisition, storage and processing | |

## Requirements at system level

The node requirements above come from the hardware design. The elicitation matrix lists system-level needs that go beyond the node. They are tracked in the [elicitation matrix](elicitation-matrix.md#base-requirements) as `REQ-01` to `REQ-16`, and mapped to epics in the [user stories](epics-and-user-stories.md).

## Gaps to close

1. Autonomy period (FR-11, NFR-01, NFR-02). Without it we cannot size the battery or decide whether solar is needed.
2. Storage period (NFR-05). Tied to the retention question EL-09.
3. Where exactly the temperature and humidity are measured: brood nest, honey super or outside. The backlog story US3 says "brood nest and honey super zones", which implies two sensors.
4. Camera model and mounting (FR-03). The [camera document](https://github.com/endlessconflict/SmartHive-Vision/blob/main/docs/02-camera-and-optics.md) gives the constraints that the choice must satisfy.
