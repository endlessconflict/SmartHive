# SmartHive backlog (generated)

Generated from [`backlog.yaml`](backlog.yaml) by `python docs/jira/build.py`. Edit the YAML, not this file.

49 stories and tasks, 141 sub-tasks, 267 story points (91 done).

## Sprints

| Sprint | Dates | Goal | Points | Done |
|---|---|---|---|---|
| SH Sprint 3 | 2026-09-28 to 2026-10-11 | Foundations: documented architecture, synthetic data generators and a first trained vision model | 78 | 78 |
| SH Sprint 4 | 2026-10-12 to 2026-10-25 | Contracts frozen, Compose stack up, camera chosen, client interview done | 30 | 13 |
| SH Sprint 5 | 2026-10-26 to 2026-11-08 | First end-to-end slice: a DHT11 reading and a simulated hive both reach the dashboard | 41 | 0 |
| SH Sprint 6 | 2026-11-09 to 2026-11-22 | Vision on the node: detections become events | 27 | 0 |
| SH Sprint 7 | 2026-11-23 to 2026-12-06 | Alerts: a hornet in front of the camera becomes an email | 31 | 0 |
| SH Sprint 8 | 2026-12-07 to 2026-12-20 | Intelligence: anomaly detection on synthetic telemetry, Varroa index in the UI | 28 | 0 |
| SH Sprint 9 | 2027-01-04 to 2027-01-17 | Evaluation report per data tier; optional yield proof of concept | 19 | 0 |
| SH Sprint 10 | 2027-01-18 to 2027-01-31 | Field install, soak test, final demo | 13 | 0 |

## Load per person and sprint (story points)

| Person | Sprint 3 | Sprint 4 | Sprint 5 | Sprint 6 | Sprint 7 | Sprint 8 | Sprint 9 | Sprint 10 |
|---|---|---|---|---|---|---|---|---|
| James Tack | 3 |  | 10 |  | 8 |  | 3 |  |
| Ricardo Villarreal |  | 6 | 10 | 13 |  | 13 |  | 5 |
| Adrien Cubilla | 67 | 3 | 8 | 11 | 13 |  |  | 8 |
| Diego Alejandro Vasquez | 8 |  |  |  |  | 13 | 14 |  |
| Karen Jimenez |  | 10 | 5 |  | 5 |  |  |  |
| Maria de los Angeles Agudelo |  | 11 | 8 | 3 | 5 | 2 | 2 |  |

## E1 Sensor node & IoT connectivity

EPIC 1 of the project plan. The Raspberry Pi 3B node measures the hive's internal climate (and later weight), stores readings locally and sends them securely to the server.

Owner: Ricardo Villarreal. Component: `edge`.

| ID | Type | Summary | Pts | Sprint | Assignee | Status |
|---|---|---|---|---|---|---|
| [HW-01](#hw-01) | Task | Choose, mount and characterize the entrance camera | 5 | Sprint 4 | Ricardo Villarreal | To Do |
| [US01](#us01) | Story | Continuous internal temperature and humidity measurement | 5 | Sprint 5 | Ricardo Villarreal | To Do |
| [US02](#us02) | Story | Continuous hive weight measurement | 8 | Sprint 8 | Ricardo Villarreal | To Do |
| [US03](#us03) | Story | Local data storage and offline synchronization | 5 | Sprint 5 | Karen Jimenez | To Do |
| [US04](#us04) | Story | Data encryption and in-transit protection | 5 | Sprint 4 | Karen Jimenez | Done |
| [US05](#us05) | Story | Centralized data synchronization | 5 | Sprint 5 | James Tack | To Do |
| [US06](#us06) | Story | Device connection loss and power alert | 5 | Sprint 7 | Karen Jimenez | To Do |
| [HW-02](#hw-02) | Task | Power feed for the demo and measured power budget | 5 | Sprint 5 | Ricardo Villarreal | To Do |
| [HW-03](#hw-03) | Task | Weatherproof enclosure and sensor cabling | 5 | Sprint 8 | Ricardo Villarreal | To Do |
| [HW-04](#hw-04) | Task | Field installation and 48 h soak test | 5 | Sprint 10 | Ricardo Villarreal | To Do |

### HW-01

**Choose, mount and characterize the entrance camera** (Task, Highest, 5 pts, SH Sprint 4, Ricardo Villarreal, To Do)

> As the team, we need a camera that gives >= 8 px/mm on the landing board so that Varroa is visible to the model.

Acceptance criteria:

1. Given the mounting distance, when a ruler is photographed on the board, then the measured px/mm is >= 8 and recorded in the generator config
2. Given the camera, when 200+ empty-board frames across a day are captured, then they are stored as tier C backgrounds
3. Given a gray card at several light levels, when captured, then the noise profile is fitted for the generator

Design: [docs/03-vision/02-camera-and-optics.md](../../docs/03-vision/02-camera-and-optics.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| HW-01.1 Select camera (CSI preferred) and lens focus for 10-25 cm | Ricardo Villarreal | 3 | To Do |
| HW-01.2 Mount with shade hood; ruler frame; px/mm | Ricardo Villarreal | 3 | To Do |
| HW-01.3 Tier C capture session (backgrounds, gray card) | Adrien Cubilla | 3 | To Do |

### US01

**Continuous internal temperature and humidity measurement** (Story, Highest, 5 pts, SH Sprint 5, Ricardo Villarreal, To Do)

> As a beekeeper, I want the hive to continuously measure internal temperature and humidity so that I can monitor environmental conditions remotely.

Acceptance criteria:

1. Given dtoverlay=dht11 on GPIO4, when sensord runs, then a reading with quality flag is stored every configured interval (default 60 s)
2. Given a failed read, when it happens, then one retry is made and otherwise a read_error row is stored, never a fake value
3. Given the probe, when installed, then it sits in the brood nest on a cable, away from the Pi's heat

Design: [docs/05-backend/03-edge-node-software.md](../../docs/05-backend/03-edge-node-software.md), [docs/02-hardware/hardware-review-notes.md](../../docs/02-hardware/hardware-review-notes.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US01.1 Kernel IIO driver setup and sensord service | Ricardo Villarreal | 4 | To Do |
| US01.2 Fake sensor reading simulator output for tests | Diego Alejandro Vasquez | 2 | To Do |

### US02

**Continuous hive weight measurement** (Story, High, 8 pts, SH Sprint 8, Ricardo Villarreal, To Do)

> As a beekeeper, I want the hive to continuously measure its weight so that I can track nectar accumulation without a physical visit.

Acceptance criteria:

1. Given an HX711 and load cell under the hive, when calibrated with known masses, then readings are within the simulator's assumed noise (about 30 g)
2. Given weight readings, when published, then they use quantity=weight in kg and need no backend change

Design: [docs/02-hardware/electrical-design-prototype-1.md](../../docs/02-hardware/electrical-design-prototype-1.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US02.1 Wire HX711 and load cell; add to schematic | Ricardo Villarreal | 5 | To Do |
| US02.2 Calibration procedure and temperature coefficient measurement | Ricardo Villarreal | 3 | To Do |

### US03

**Local data storage and offline synchronization** (Story, High, 5 pts, SH Sprint 5, Karen Jimenez, To Do)

> As a beekeeper, I want the collected data to be saved locally if the Internet connection is lost, and synchronized once the connection is restored.

Acceptance criteria:

1. Given the broker is unreachable, when readings are produced, then they accumulate in the SQLite outbox
2. Given the broker comes back, when uplinkd reconnects, then events are sent first, then telemetry oldest first, and rows are marked sent only after PUBACK
3. Given storage runs low, when data must be dropped, then the drop is counted in health messages

Design: [docs/05-backend/03-edge-node-software.md](../../docs/05-backend/03-edge-node-software.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US03.1 Outbox schema and batching writer | Karen Jimenez | 3 | To Do |
| US03.2 uplinkd publish loop with backoff and PUBACK marking | Karen Jimenez | 5 | To Do |

### US04

**Data encryption and in-transit protection** (Story, High, 5 pts, SH Sprint 4, Karen Jimenez, Done)

> As a system administrator, I want hive information to be protected while it travels to the system, so that no one else can see or tamper with it.

Acceptance criteria:

1. Given the broker, when a client connects on 1883 from the LAN, then it is refused; 8883 with TLS is the only external port
2. Given device credentials, when a node publishes to another node's topic, then the ACL denies it

Design: [docs/05-backend/08-deployment-and-operations.md](../../docs/05-backend/08-deployment-and-operations.md), [docs/05-backend/04-messaging-contract.md](../../docs/05-backend/04-messaging-contract.md)

Evidence: [infra/pki/make-ca.sh](../../infra/pki/make-ca.sh), [infra/mosquitto/mosquitto.conf](../../infra/mosquitto/mosquitto.conf), [infra/mosquitto/acl](../../infra/mosquitto/acl), [infra/mosquitto/test_broker.sh](../../infra/mosquitto/test_broker.sh)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US04.1 Local CA and certificate scripts | Karen Jimenez | 3 | Done |
| US04.2 Mosquitto TLS, password file and pattern ACLs | Karen Jimenez | 3 | Done |

### US05

**Centralized data synchronization** (Story, High, 5 pts, SH Sprint 5, James Tack, To Do)

> As a system administrator, I want all hive information to arrive at one central place, so that every part of the system uses the same, consistent data.

Acceptance criteria:

1. Given a valid telemetry batch, when ingested, then rows are inserted once even if the batch arrives twice
2. Given an invalid payload, when received, then it is rejected, logged and does not stop ingestion

Blocked by: [EN-07](#en-07), [EN-08](#en-08)

Design: [docs/05-backend/05-data-model.md](../../docs/05-backend/05-data-model.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US05.1 Ingestor with schema validation and idempotent inserts | James Tack | 6 | To Do |
| US05.2 Integration test with Testcontainers | James Tack | 3 | To Do |

### US06

**Device connection loss and power alert** (Story, Medium, 5 pts, SH Sprint 7, Karen Jimenez, To Do)

> As a beekeeper, I want to be warned when a hive stops sending information, so that I can check whether the device has run out of power or lost its connection.

Acceptance criteria:

1. Given a node loses power, when the broker publishes its last will, then a node_offline warning opens within N heartbeats
2. Given an INA219 is fitted, when voltage drops before silence, then the alert says 'probably battery'

Design: [docs/02-hardware/power-budget.md](../../docs/02-hardware/power-budget.md), [docs/05-backend/07-alerts-and-rules.md](../../docs/05-backend/07-alerts-and-rules.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US06.1 Last will + heartbeat timeout rule | James Tack | 3 | To Do |
| US06.2 INA219 battery monitor and health field | Ricardo Villarreal | 4 | To Do |

### HW-02

**Power feed for the demo and measured power budget** (Task, High, 5 pts, SH Sprint 5, Ricardo Villarreal, To Do)

> As the team, we need the node powered for days and its real consumption measured so that the autonomy requirement can be set with numbers.

Acceptance criteria:

1. Given an INA219 or USB meter, when the full software runs for 24 h, then idle, motion, detector and night-mode consumption replace the estimates in the power budget
2. Given a passive PoE feed over the existing Ethernet cable, when the battery is the backup, then the node runs for 48 h without intervention

Design: [docs/02-hardware/power-budget.md](../../docs/02-hardware/power-budget.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| HW-02.1 Wire INA219 on I2C and log consumption | Ricardo Villarreal | 4 | To Do |
| HW-02.2 Passive PoE injector/splitter into the buck input | Ricardo Villarreal | 3 | To Do |
| HW-02.3 Update power budget with measured numbers | Ricardo Villarreal | 2 | To Do |

### HW-03

**Weatherproof enclosure and sensor cabling** (Task, Medium, 5 pts, SH Sprint 8, Ricardo Villarreal, To Do)

> As the team, we need an enclosure that keeps the node dry, cool enough and away from propolis so that it survives outdoors (NFR-03, NFR-04, NFR-07).

Acceptance criteria:

1. Given 30 min of detector duty in the sun, when SoC temperature is logged, then it stays below the 80 C throttling point
2. Given the DHT11 on a cable in the brood nest, when installed, then it is away from the Pi's heat and protected from propolis

Design: [docs/02-hardware/hardware-review-notes.md](../../docs/02-hardware/hardware-review-notes.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| HW-03.1 Enclosure with ventilation and shade hood | Ricardo Villarreal | 5 | To Do |
| HW-03.2 Thermal test in the sun | Ricardo Villarreal | 2 | To Do |

### HW-04

**Field installation and 48 h soak test** (Task, Highest, 5 pts, SH Sprint 10, Ricardo Villarreal, To Do)

> As the team, we need the complete node running on a real (or simulated) hive for two days so that the demo is not its first run (REQ-15).

Acceptance criteria:

1. Given the installed node, when 48 h pass, then telemetry, events and images reach the server with no unexplained gaps

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| HW-04.1 Install and run 48 h | Ricardo Villarreal | 6 | To Do |
| HW-04.2 Collect tier F frames for the final evaluation | Adrien Cubilla | 3 | To Do |

## E2 Pest & threat detection

EPIC 2. The entrance camera and a two-stage model on the node detect hornets, small hive beetles and Varroa-carrying bees, and turn them into events and alerts.

Owner: Adrien Cubilla. Component: `vision`.

| ID | Type | Summary | Pts | Sprint | Assignee | Status |
|---|---|---|---|---|---|---|
| [US07](#us07) | Story | Periodic hive entrance image capture | 5 | Sprint 6 | Ricardo Villarreal | To Do |
| [US08](#us08) | Story | Storage optimization based on relevance | 3 | Sprint 6 | Adrien Cubilla | To Do |
| [US09](#us09) | Story | Automated Varroa mite detection | 13 | Sprint 7 | Adrien Cubilla | In Progress |
| [US10](#us10) | Story | Small hive beetle and Asian hornet detection | 8 | Sprint 6 | Adrien Cubilla | In Progress |
| [US11](#us11) | Story | Edge AI detection model execution | 8 | Sprint 6 | Ricardo Villarreal | In Progress |
| [US12](#us12) | Story | Multi-channel threat & pest notifications | 8 | Sprint 7 | James Tack | To Do |

### US07

**Periodic hive entrance image capture** (Story, High, 5 pts, SH Sprint 6, Ricardo Villarreal, To Do)

> As a beekeeper, I want the system to capture periodic images of the hive entrance so that bee traffic and potential intruders can be analyzed automatically.

Acceptance criteria:

1. Given the node by day, when camd runs, then a low-res stream is analyzed for motion and a full-res still is taken on motion
2. Given night mode hours, when the clock enters them, then the camera stops and the sensors keep running
3. Given a configurable interval, when no motion happens for an hour, then one periodic image is still kept for the dashboard

Blocked by: [HW-01](#hw-01)

Design: [docs/03-vision/06-edge-deployment.md](../../docs/03-vision/06-edge-deployment.md), [docs/03-vision/02-camera-and-optics.md](../../docs/03-vision/02-camera-and-optics.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US07.1 picamera2 dual stream (or V4L2) capture service | Ricardo Villarreal | 5 | To Do |
| US07.2 Motion gate (vision/pipeline.py MotionGate) wired to capture | Adrien Cubilla | 2 | To Do |
| US07.3 Night mode and periodic sample | Ricardo Villarreal | 2 | To Do |

### US08

**Storage optimization based on relevance** (Story, Medium, 3 pts, SH Sprint 6, Adrien Cubilla, To Do)

> As a beekeeper, I want the system to store only images where something relevant is detected so that storage is used efficiently.

Acceptance criteria:

1. Given an analyzed frame with no threat and no Varroa-positive bee, when processing ends, then the full frame is not written to the SD card
2. Given a threat or a Varroa-positive bee, when processing ends, then the frame and its crops are saved and queued for upload

Blocked by: [US11](#us11)

Design: [docs/05-backend/03-edge-node-software.md](../../docs/05-backend/03-edge-node-software.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US08.1 Keep/discard rule and tmpfs frame handling | Adrien Cubilla | 3 | To Do |
| US08.2 Image table in the outbox with upload state | Karen Jimenez | 2 | To Do |

### US09

**Automated Varroa mite detection** (Story, Highest, 13 pts, SH Sprint 7, Adrien Cubilla, In Progress)

> As a beekeeper, I want the system to automatically identify Varroa mites on returning bees so that I can start treatment before the infestation spreads.

Acceptance criteria:

1. Given a sharp bee crop at >= 8 px/mm, when stage 2 runs, then it outputs p(varroa) and the frame record carries it
2. Given synthetic validation crops (held-out sprites), when evaluated, then recall and precision for varroa are reported (tier S)
3. Given the public Varroa datasets, when available, then recall >= 0.75 and precision >= 0.70 on their test split (tier P target)
4. Given a rolling window, when bees are classified, then the Varroa index is reported with its count and 95 % Wilson interval

Design: [docs/03-vision/04-model-architecture.md](../../docs/03-vision/04-model-architecture.md), [docs/03-vision/05-training-and-evaluation.md](../../docs/03-vision/05-training-and-evaluation.md)

Evidence: [vision/pipeline.py](../../vision/pipeline.py), [docs/03-vision/07-results.md](../../docs/03-vision/07-results.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US09.1 Train stage 2 classifier on hybrid synthetic crops (v0.2) | Adrien Cubilla | 3 | Done |
| US09.2 Varroa index with Wilson interval in the aggregator | Adrien Cubilla | 2 | Done |
| US09.3 Evaluate on public Varroa crops (VarroaDataset) when downloaded | Adrien Cubilla | 3 | To Do |
| US09.4 Bee tracking across frames to count individuals (v2) | Adrien Cubilla | 8 | To Do |

### US10

**Small hive beetle and Asian hornet detection** (Story, Highest, 8 pts, SH Sprint 6, Adrien Cubilla, In Progress)

> As a beekeeper, I want the system to detect small hive beetles and Asian hornets at the entrance so that I can intervene before they damage the colony.

Acceptance criteria:

1. Given a frame, when stage 1 runs, then bee, hornet, shb and other_insect are detected with per-class thresholds
2. Given the tier P iNaturalist test split, when evaluated, then hornet recall and bee/hornet/other accuracy are reported against chance
3. Given k-of-n aggregation, when a hornet appears in 3 of 10 analyzed frames, then exactly one threat_detected event is raised per episode

Design: [docs/03-vision/04-model-architecture.md](../../docs/03-vision/04-model-architecture.md), [docs/03-vision/07-results.md](../../docs/03-vision/07-results.md)

Evidence: [vision/train.py](../../vision/train.py), [vision/eval_real.py](../../vision/eval_real.py), [vision/pipeline.py](../../vision/pipeline.py)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US10.1 Train stage 1 detector on synthetic scenes (iterations v0.1 to v0.3) | Adrien Cubilla | 6 | Done |
| US10.2 Tier P evaluation script and report | Adrien Cubilla | 3 | Done |
| US10.3 k-of-n aggregator with self-check | Adrien Cubilla | 2 | Done |
| US10.4 Raise SHB tier P coverage (more photos, field captures) | Adrien Cubilla | 4 | To Do |

### US11

**Edge AI detection model execution** (Story, High, 8 pts, SH Sprint 6, Ricardo Villarreal, In Progress)

> As a beekeeper, I want the pest detection model to run directly on the sensor node so that detections happen even with limited connectivity.

Acceptance criteria:

1. Given trained weights, when exported, then ncnn param/bin files load with the ncnn Python bindings and no torch
2. Given the Pi 3B, when the benchmark runs with the node software active, then stage 1 p95 <= 1.0 s and a frame with 15 bees p95 <= 2.0 s
3. Given the vision service, when running, then its RSS stays under its 250 MB systemd limit

Blocked by: [HW-01](#hw-01)

Design: [docs/03-vision/06-edge-deployment.md](../../docs/03-vision/06-edge-deployment.md)

Evidence: [vision/export.py](../../vision/export.py), [vision/bench.py](../../vision/bench.py), [vision/pipeline.py](../../vision/pipeline.py)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US11.1 Export to ncnn and torch-free two-stage pipeline | Adrien Cubilla | 4 | Done |
| US11.2 Pi latency estimate anchored to ncnn's published Pi 3B+ benchmarks | Adrien Cubilla | 2 | Done |
| US11.3 Run vision/bench.py on the real Pi 3B and replace the estimate | Ricardo Villarreal | 2 | To Do |
| US11.4 visiond systemd unit with MemoryMax | Ricardo Villarreal | 2 | To Do |

### US12

**Multi-channel threat & pest notifications** (Story, Highest, 8 pts, SH Sprint 7, James Tack, To Do)

> As a beekeeper, I want to receive an in-app and email alert when a pest or intruder is detected so that I can act quickly without constantly checking the dashboard.

Acceptance criteria:

1. Given a threat_detected event, when the worker processes it, then one alert opens (dedup per episode) and in-app plus email notifications are sent within 10 s
2. Given the mail server is down, when notifications fail, then they are retried and not lost
3. Given a simulated node, when an event fires, then no email is sent unless the demo profile allows it

Blocked by: [EN-07](#en-07), [EN-08](#en-08)

Design: [docs/05-backend/07-alerts-and-rules.md](../../docs/05-backend/07-alerts-and-rules.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US12.1 Event rules and alert lifecycle in the worker | James Tack | 6 | To Do |
| US12.2 SMTP and in-app channels with retries; Mailpit in dev | James Tack | 4 | To Do |
| US12.3 Notification inbox in the dashboard | Maria de los Angeles Agudelo | 4 | To Do |

## E3 Colony dashboard

EPIC 3. History, latest image, alert log and anomaly warnings for each colony.

Owner: Maria de los Angeles Agudelo. Component: `frontend`.

| ID | Type | Summary | Pts | Sprint | Assignee | Status |
|---|---|---|---|---|---|---|
| [US13](#us13) | Story | Historical environmental data & trend view | 8 | Sprint 5 | Maria de los Angeles Agudelo | To Do |
| [US14](#us14) | Story | Alert history and response log | 5 | Sprint 7 | Maria de los Angeles Agudelo | To Do |
| [US15](#us15) | Story | Latest hive entrance camera image view | 3 | Sprint 6 | Maria de los Angeles Agudelo | To Do |
| [US16](#us16) | Story | Flagging unusual hive behavior patterns | 8 | Sprint 8 | Diego Alejandro Vasquez | To Do |
| [US17](#us17) | Story | Preventive anomaly dashboard warnings | 2 | Sprint 8 | Maria de los Angeles Agudelo | To Do |

### US13

**Historical environmental data & trend view** (Story, High, 8 pts, SH Sprint 5, Maria de los Angeles Agudelo, To Do)

> As a beekeeper, I want to see how my hive's conditions have changed over time, so that I can understand how the colony is doing and spot problems early.

Acceptance criteria:

1. Given a hive, when the user picks 24 h, 7 d, 30 d or a custom range, then temperature, humidity and weight charts load with gaps shown as gaps
2. Given simulated hives, when shown, then a visible badge marks them as simulated

Blocked by: [EN-02](#en-02)

Design: [docs/05-backend/06-api-design.md](../../docs/05-backend/06-api-design.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US13.1 Readings endpoint with time_bucket | James Tack | 4 | To Do |
| US13.2 Chart view and range picker | Maria de los Angeles Agudelo | 6 | To Do |

### US14

**Alert history and response log** (Story, Medium, 5 pts, SH Sprint 7, Maria de los Angeles Agudelo, To Do)

> As a beekeeper, I want to see the alert history for a colony so that I can review past events and my responses to them.

Acceptance criteria:

1. Given an alert, when acknowledged or resolved with a note, then the log shows who and when

Blocked by: [US12](#us12)

Design: [docs/05-backend/07-alerts-and-rules.md](../../docs/05-backend/07-alerts-and-rules.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US14.1 Alert endpoints and event log | James Tack | 3 | To Do |
| US14.2 Alert history UI | Maria de los Angeles Agudelo | 4 | To Do |

### US15

**Latest hive entrance camera image view** (Story, Medium, 3 pts, SH Sprint 6, Maria de los Angeles Agudelo, To Do)

> As a beekeeper, I want to see the latest entrance camera image for a colony so that I can visually confirm what the system detected.

Acceptance criteria:

1. Given an uploaded image, when the hive page opens, then the latest image shows with its detected boxes
2. Given the refresh button, when pressed, then a capture_now command is sent to the node

Design: [docs/05-backend/06-api-design.md](../../docs/05-backend/06-api-design.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US15.1 Image upload endpoint and storage | James Tack | 4 | To Do |
| US15.2 Latest image component with boxes | Maria de los Angeles Agudelo | 3 | To Do |

### US16

**Flagging unusual hive behavior patterns** (Story, Medium, 8 pts, SH Sprint 8, Diego Alejandro Vasquez, To Do)

> As a beekeeper, I want the system to flag unusual hive behavior that does not match any known pattern so that I can investigate even when the cause is not yet identified.

Acceptance criteria:

1. Given the abscond_and_collapse scenario (never seen in training), when the model runs, then event recall and detection delay are reported
2. Given quiet_hive, when the model runs for a year, then false alerts per hive per week are reported

Design: [docs/04-data/03-scenarios-and-events.md](../../docs/04-data/03-scenarios-and-events.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US16.1 Daily feature extraction from telemetry | Diego Alejandro Vasquez | 4 | To Do |
| US16.2 Baselines: robust z-scores, seasonal residuals, Isolation Forest | Diego Alejandro Vasquez | 6 | To Do |
| US16.3 Event-level evaluation on known vs novel events | Diego Alejandro Vasquez | 4 | To Do |

### US17

**Preventive anomaly dashboard warnings** (Story, Medium, 2 pts, SH Sprint 8, Maria de los Angeles Agudelo, To Do)

> As a beekeeper, I want anomalies to appear in the dashboard as a warning rather than a critical alert so that I can review them without feeling pressured to act immediately.

Acceptance criteria:

1. Given an anomaly window, when shown, then it appears as a warning band on the charts and no notification is sent

Blocked by: [US16](#us16)

Design: [docs/05-backend/07-alerts-and-rules.md](../../docs/05-backend/07-alerts-and-rules.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US17.1 Warning band on charts | Maria de los Angeles Agudelo | 3 | To Do |

## E4 Honey flow & yield optimization (optional)

EPIC 4, optional. 7-day yield estimate as a range, and super/harvest recommendations. Only if Epics 1 to 3 are on track.

Owner: Diego Alejandro Vasquez. Component: `ml`.

| ID | Type | Summary | Pts | Sprint | Assignee | Status |
|---|---|---|---|---|---|---|
| [US18](#us18) | Story | 7-day honey production yield estimation | 8 | Sprint 9 | Diego Alejandro Vasquez | To Do |
| [US19](#us19) | Story | Prediction range visualization | 2 | Sprint 9 | Maria de los Angeles Agudelo | To Do |
| [US20](#us20) | Story | Weather data integration for yield accuracy | 3 | Sprint 9 | James Tack | To Do |
| [US21](#us21) | Story | Optimal honey super addition recommendation | 3 | Sprint 9 | Diego Alejandro Vasquez | To Do |
| [US22](#us22) | Story | Optimal honey harvest timing recommendation | 3 | Sprint 9 | Diego Alejandro Vasquez | To Do |

### US18

**7-day honey production yield estimation** (Story, Low, 8 pts, SH Sprint 9, Diego Alejandro Vasquez, To Do)

> As a beekeeper, I want the system to estimate how much honey my hive will produce in the next 7 days so that I can plan my harvest in advance.

Acceptance criteria:

1. Given simulated history, when the model predicts, then it beats 'same as last week' and 'seasonal mean' baselines on held-out hives

Design: [docs/04-data/03-scenarios-and-events.md](../../docs/04-data/03-scenarios-and-events.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US18.1 Label function (net gain excluding management) | Diego Alejandro Vasquez | 2 | To Do |
| US18.2 Quantile model and baselines | Diego Alejandro Vasquez | 6 | To Do |

### US19

**Prediction range visualization** (Story, Low, 2 pts, SH Sprint 9, Maria de los Angeles Agudelo, To Do)

> As a beekeeper, I want the prediction to be shown as a range rather than an exact number so that I understand there is inherent uncertainty in the estimate.

Acceptance criteria:

1. Given a prediction with p10/p50/p90, when shown, then the range is drawn and the point estimate is secondary

Blocked by: [US18](#us18)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US19.1 Range chart component | Maria de los Angeles Agudelo | 3 | To Do |

### US20

**Weather data integration for yield accuracy** (Story, Low, 3 pts, SH Sprint 9, James Tack, To Do)

> As a beekeeper, I want the system to combine hive weight data with local weather information to improve the accuracy of the yield prediction.

Acceptance criteria:

1. Given the apiary coordinates, when the worker runs daily, then Open-Meteo forecast and history are stored per apiary

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US20.1 Open-Meteo client and weather table | James Tack | 3 | To Do |

### US21

**Optimal honey super addition recommendation** (Story, Low, 3 pts, SH Sprint 9, Diego Alejandro Vasquez, To Do)

> As a beekeeper, I want to receive a recommendation when conditions are optimal to add a honey super so that I can maximize production without intervening too early.

Acceptance criteria:

1. Given predicted stores above 70 % of capacity during a flow, when the rule runs, then an informative recommendation appears (EL-11 assumption)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US21.1 Rule and evaluation on simulated super_added events | Diego Alejandro Vasquez | 3 | To Do |

### US22

**Optimal honey harvest timing recommendation** (Story, Low, 3 pts, SH Sprint 9, Diego Alejandro Vasquez, To Do)

> As a beekeeper, I want to receive a recommendation when the honey is ready to harvest so that I do not extract too early or miss the right window.

Acceptance criteria:

1. Given the end of a flow and stores above the reserve, when the rule runs, then a harvest recommendation appears, checked against simulated harvest events

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| US22.1 Rule and evaluation on simulated harvest events | Diego Alejandro Vasquez | 3 | To Do |

## E5 Synthetic data platform

New epic created when the client confirmed there is no data. Generators for hive telemetry and entrance images, a real-image check set, dataset governance.

Owner: Diego Alejandro Vasquez. Component: `simulation`.

| ID | Type | Summary | Pts | Sprint | Assignee | Status |
|---|---|---|---|---|---|---|
| [EN-01](#en-01) | Story | Hive telemetry simulator v1 with stylized-fact tests | 8 | Sprint 3 | Diego Alejandro Vasquez | Done |
| [EN-01b](#en-01b) | Story | Calibrate the telemetry simulator against real hive series | 5 | Sprint 8 | Diego Alejandro Vasquez | To Do |
| [EN-02](#en-02) | Story | MQTT replay of simulated hives (fake nodes) | 5 | Sprint 5 | James Tack | To Do |
| [EN-03](#en-03) | Story | Procedural insect renderer (license-free sprites) | 8 | Sprint 3 | Adrien Cubilla | Done |
| [EN-04](#en-04) | Story | Entrance scene compositor with exact labels | 8 | Sprint 3 | Adrien Cubilla | Done |
| [EN-05](#en-05) | Story | Real-image check set (tier P) from the iNaturalist Open Dataset | 5 | Sprint 3 | Adrien Cubilla | Done |
| [EN-06](#en-06) | Task | Dataset versioning with DVC and dataset cards | 3 | Sprint 4 | Maria de los Angeles Agudelo | In Progress |
| [EN-10](#en-10) | Story | Hybrid sprite library with real-photo cutouts (vision iteration v0.2) | 5 | Sprint 3 | Adrien Cubilla | Done |
| [EN-11](#en-11) | Story | Vision iteration v0.3 (distractors), model release v0.2 and per-tier results report | 5 | Sprint 3 | Adrien Cubilla | Done |
| [EN-13](#en-13) | Story | Vision iteration v0.4 (real photos with automatic labels) and model release v0.4 | 5 | Sprint 3 | Adrien Cubilla | Done |
| [EN-14](#en-14) | Story | Real-photo data v2 (iNaturalist 2026 snapshot, tier P v2, Open Images) | 8 | Sprint 3 | Adrien Cubilla | Done |
| [EN-15](#en-15) | Story | Automatic labeling with OSI-licensed weights only, scored against human boxes | 5 | Sprint 3 | Adrien Cubilla | Done |
| [EN-16](#en-16) | Story | Species verifier (stage 1b) for hornet and other-insect detections | 5 | Sprint 3 | Adrien Cubilla | Done |
| [EN-17](#en-17) | Story | Vision iteration v0.5 (YOLO26n detector, clean data, release v0.5) | 8 | Sprint 3 | Adrien Cubilla | Done |
| [EN-12](#en-12) | Story | Vision iteration v0.6 (real backgrounds, 416 px trial, Varroa threshold) | 8 | Sprint 5 | Adrien Cubilla | To Do |

### EN-01

**Hive telemetry simulator v1 with stylized-fact tests** (Story, Highest, 8 pts, SH Sprint 3, Diego Alejandro Vasquez, Done)

> As the ML and backend teams, we need realistic simulated hive telemetry with labeled events so that we can build and test models and the dashboard without client data.

Acceptance criteria:

1. Given a scenario YAML and a seed, when the simulator runs, then it writes telemetry, events, colony ground truth, weather and a manifest, identical on every run
2. Given the default scenario, when the stylized-fact tests run, then brood temperature, daily weight cycle, rain, swarm, absconding and humidity facts all pass
3. Given the observed columns, when compared with the DHT11 datasheet, then values are integers within its range and carry quality flags
4. Given six scenarios (baseline, swarm season, abscond/collapse, sensor faults, quiet hive, battery node), when generated with seed 42, then all finish in under a minute

Design: [docs/04-data/02-hive-telemetry-simulator.md](../../docs/04-data/02-hive-telemetry-simulator.md), [docs/04-data/03-scenarios-and-events.md](../../docs/04-data/03-scenarios-and-events.md), [docs/04-data/04-sensor-and-node-realism.md](../../docs/04-data/04-sensor-and-node-realism.md)

Evidence: [simulation/telemetry/sim.py](../../simulation/telemetry/sim.py), [simulation/telemetry/test_sim.py](../../simulation/telemetry/test_sim.py)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-01.1 Weather, bloom and flight model | Diego Alejandro Vasquez | 4 | Done |
| EN-01.2 Colony, foraging, weight, temperature and humidity models | Diego Alejandro Vasquez | 8 | Done |
| EN-01.3 Colony and management events with labels | Diego Alejandro Vasquez | 4 | Done |
| EN-01.4 DHT11/HX711 and node outage/clock model | Ricardo Villarreal | 3 | Done |
| EN-01.5 Stylized-fact tests and seed sweep | Diego Alejandro Vasquez | 3 | Done |
| EN-01.6 Scenario files and docs figure | Diego Alejandro Vasquez | 2 | Done |

### EN-01b

**Calibrate the telemetry simulator against real hive series** (Story, Medium, 5 pts, SH Sprint 8, Diego Alejandro Vasquez, To Do)

> As the ML team, we need the simulator's parameter ranges checked against real measurements so that models trained on it transfer to a real hive.

Acceptance criteria:

1. Given MSPB (or our node's own data), when summary statistics are computed (daily amplitude, autocorrelation, event signatures), then simulated and real values overlap, or the ranges are tightened until they do
2. Given real weather history for the apiary's coordinates, when it replaces the stochastic weather, then the tests still pass

Design: [docs/04-data/02-hive-telemetry-simulator.md](../../docs/04-data/02-hive-telemetry-simulator.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-01b.1 Download MSPB on a machine with Zenodo access; compute summary statistics | Diego Alejandro Vasquez | 4 | To Do |
| EN-01b.2 Optional Open-Meteo history provider with Parquet cache | James Tack | 3 | To Do |
| EN-01b.3 Tighten parameter ranges and record before/after in the doc | Diego Alejandro Vasquez | 3 | To Do |

### EN-02

**MQTT replay of simulated hives (fake nodes)** (Story, High, 5 pts, SH Sprint 5, James Tack, To Do)

> As the backend and frontend developers, we want simulated hives to publish over the real MQTT contract so that we can build and demo the system before the hardware is ready.

Acceptance criteria:

1. Given a generated telemetry dataset, when replay runs at speed N, then each sim- hive publishes valid telemetry, status and health messages on smarthive/v1/nodes/{node_id}/...
2. Given node outages in the dataset, when replayed, then the fake node goes offline (last will) and later sends its backlog, with some duplicates, like a real node
3. Given the demo_day scenario, when replayed at 1x, then a swarm at 11:00 and a node dropout at 16:00 happen on schedule

Blocked by: [EN-07](#en-07)

Design: [docs/05-backend/04-messaging-contract.md](../../docs/05-backend/04-messaging-contract.md), [docs/04-data/04-sensor-and-node-realism.md](../../docs/04-data/04-sensor-and-node-realism.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-02.1 Replay CLI publishing from Parquet with paho-mqtt | James Tack | 5 | To Do |
| EN-02.2 Transport model: duplicates, late batches, reordering | Karen Jimenez | 3 | To Do |
| EN-02.3 demo_day scenario with scripted events | Diego Alejandro Vasquez | 3 | To Do |
| EN-02.4 Contract test: replay output validates against JSON Schemas | Karen Jimenez | 2 | To Do |

### EN-03

**Procedural insect renderer (license-free sprites)** (Story, Highest, 8 pts, SH Sprint 3, Adrien Cubilla, Done)

> As the vision team, we need labeled images of bees, Varroa, hornets, beetles and distractors without any licensed photo so that training data is unlimited and free to publish.

Acceptance criteria:

1. Given a species and px/mm, when a sprite is rendered, then its size follows real body lengths (bee 12-15 mm, hornet 20-30 mm, SHB 5-7 mm, Varroa 1.6 x 1.1 mm)
2. Given a bee with mites, when rendered, then each mite sits on the dorsal thorax or abdomen and its pixel footprint matches 1.6 mm at that scale (test)
3. Given the renderer, when reviewed, then no external image or 3D model is used

Design: [docs/03-vision/03-synthetic-image-pipeline.md](../../docs/03-vision/03-synthetic-image-pipeline.md)

Evidence: [simulation/images/render.py](../../simulation/images/render.py), [simulation/images/test_images.py](../../simulation/images/test_images.py)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-03.1 Generic segmented-insect renderer (shading, bands, hair, wings, legs, antennae) | Adrien Cubilla | 8 | Done |
| EN-03.2 Species samplers: bee (incl. Africanized), hornet (velutina, crabro), SHB, fly, ant, wasp, bumblebee | Adrien Cubilla | 4 | Done |
| EN-03.3 Varroa sprite and anatomical placement; pollen loads as look-alikes | Adrien Cubilla | 3 | Done |

### EN-04

**Entrance scene compositor with exact labels** (Story, Highest, 8 pts, SH Sprint 3, Adrien Cubilla, Done)

> As the vision team, we need full entrance scenes with occlusion-aware boxes and bee crops so that both model stages can be trained.

Acceptance criteria:

1. Given a seed, when scenes are generated, then the same images and labels come out every time (test)
2. Given a scene, when labels are written, then every box lies inside the image and comes from the visible (not occluded) part of the insect
3. Given a bee crop, when it is labeled varroa, then at least one mite of that bee is visible in the scene
4. Given the dataset, when generated, then train and val use different sprite libraries and a dataset card is written

Design: [docs/03-vision/03-synthetic-image-pipeline.md](../../docs/03-vision/03-synthetic-image-pipeline.md), [docs/04-data/05-dataset-versioning-and-governance.md](../../docs/04-data/05-dataset-versioning-and-governance.md)

Evidence: [simulation/images/compose.py](../../simulation/images/compose.py)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-04.1 Procedural boards: wood, paint, chips, stains, debris, entrance slot | Adrien Cubilla | 4 | Done |
| EN-04.2 Behavioral placement, shadows, lighting, camera model | Adrien Cubilla | 5 | Done |
| EN-04.3 Occlusion-aware labels, stage 1 YOLO export, stage 2 crops, dataset card | Adrien Cubilla | 4 | Done |
| EN-04.4 Tier C: replace procedural boards with real board photos from the chosen camera | Ricardo Villarreal | 3 | To Do |

### EN-05

**Real-image check set (tier P) from the iNaturalist Open Dataset** (Story, High, 5 pts, SH Sprint 3, Adrien Cubilla, Done)

> As the vision team, we need a frozen set of real, openly licensed insect photos so that we can measure how well synthetic training transfers to real images.

Acceptance criteria:

1. Given the iNaturalist open data, when filtered, then only research-grade, CC0/CC-BY first photos of our taxa are kept
2. Given the photos, when the split is frozen, then each file has class, split (calib/test), SHA-256, license, source URL and observer
3. Given the test split, when any training config is reviewed, then no test file is used for training or tuning

Design: [docs/04-data/01-data-problem-and-strategy.md](../../docs/04-data/01-data-problem-and-strategy.md)

Evidence: [vision/inat.py](../../vision/inat.py), [vision/splits/P-inat-v1.tsv](../../vision/splits/P-inat-v1.tsv)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-05.1 Streaming filter over the 4.8 GB metadata archive | Adrien Cubilla | 3 | Done |
| EN-05.2 Download capped photos per class with manifest | Adrien Cubilla | 1 | Done |
| EN-05.3 Freeze calib/test split with checksums | Adrien Cubilla | 1 | Done |
| EN-05.4 Add the public Varroa datasets (Zenodo, Bilik et al.) from a machine with access | Adrien Cubilla | 3 | To Do |

### EN-06

**Dataset versioning with DVC and dataset cards** (Task, Medium, 3 pts, SH Sprint 4, Maria de los Angeles Agudelo, In Progress)

> As a team, we need datasets and weights versioned outside git so that any reported number can be reproduced.

Acceptance criteria:

1. Given a dataset under data/, when dvc push runs, then it is stored in the team's free remote and dvc pull restores it on another machine
2. Given a training run, when logged, then the dataset ID, generator commit and seed are recorded next to the metrics

Design: [docs/04-data/05-dataset-versioning-and-governance.md](../../docs/04-data/05-dataset-versioning-and-governance.md)

Evidence: [.dvc/config](../../.dvc/config), [vision/train.py](../../vision/train.py)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-06.1 dvc init, SSH or folder remote on the gateway PC | Maria de los Angeles Agudelo | 2 | In Progress |
| EN-06.2 Track simulation outputs, tier P split files and released weights | Adrien Cubilla | 2 | To Do |

### EN-10

**Hybrid sprite library with real-photo cutouts (vision iteration v0.2)** (Story, Highest, 5 pts, SH Sprint 3, Adrien Cubilla, Done)

> As the vision team, we need real insect appearance in the training scenes so that the detector recognizes real bees and hornets, not only drawn ones.

Acceptance criteria:

1. Given an iNaturalist asset pool disjoint from the tier P split (checked: zero overlap), when cutouts are extracted, then each has a mask from SAM 2.1 tiny, a YOLOE text-prompted box and its license and source
2. Given real bee cutouts, when used in scenes, then 45 % carry procedural mites so stage 2 cannot learn 'real-looking bee means clean'
3. Given generator v0.2 and model v0.2, when evaluated on the tier P calibration split, then accuracy is compared with v0.1 in the results document

Design: [docs/03-vision/07-results.md](../../docs/03-vision/07-results.md), [docs/03-vision/03-synthetic-image-pipeline.md](../../docs/03-vision/03-synthetic-image-pipeline.md)

Evidence: [simulation/images/cutouts.py](../../simulation/images/cutouts.py), [simulation/images/compose.py](../../simulation/images/compose.py)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-10.1 Disjoint asset pool download (600 per class) | Adrien Cubilla | 1 | Done |
| EN-10.2 YOLOE + SAM 2.1 cutout extraction with shape filters | Adrien Cubilla | 4 | Done |
| EN-10.3 Compositor: hybrid library, mites on real bees, random-texture backgrounds | Adrien Cubilla | 3 | Done |
| EN-10.4 Retrain and compare on tier P calibration split | Adrien Cubilla | 3 | Done |

### EN-11

**Vision iteration v0.3 (distractors), model release v0.2 and per-tier results report** (Story, High, 5 pts, SH Sprint 3, Adrien Cubilla, Done)

> As the vision team, we need real wasps, flies and bumblebees to stop being called hornets so that hornet alerts can be trusted.

Acceptance criteria:

1. Given a second iNaturalist pool disjoint from tier P and from the first pool, when cutouts are extracted, then real 'other' insects at least double (147 to 339)
2. Given v0.3 data, when stage 1 is fine-tuned from v0.2, then tier P calibration accuracy and the hornet false-positive count on real 'other' photos are compared with v0.2 (result: no gain, hornet false positives rose, v0.3 recorded as a negative result)
3. Given the chosen model (v0.2), when the frozen tier P test split is opened once, then its numbers are reported in the results document next to tier S, the system-level test and the latency estimate
4. Given the release, when published under models/v0.2, then it has a model card, checksums and the attribution list of the real photos

Design: [docs/03-vision/07-results.md](../../docs/03-vision/07-results.md), [models/v0.2/MODEL_CARD.md](../../models/v0.2/MODEL_CARD.md)

Evidence: [docs/03-vision/07-results.md](../../docs/03-vision/07-results.md), [models/v0.2/MODEL_CARD.md](../../models/v0.2/MODEL_CARD.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-11.1 Second disjoint pool (2,100 photos) and cutouts v2 | Adrien Cubilla | 2 | Done |
| EN-11.2 Generator v0.3: more distractors per scene, several cutout folders | Adrien Cubilla | 1 | Done |
| EN-11.3 Fine-tune from v0.2 and compare on tier P calib | Adrien Cubilla | 2 | Done |
| EN-11.4 Final tier P test, system-level test, latency estimate, results document | Adrien Cubilla | 3 | Done |
| EN-11.5 Package ncnn release v0.2: model card, SHA256SUMS, attribution | Adrien Cubilla | 1 | Done |

### EN-13

**Vision iteration v0.4 (real photos with automatic labels) and model release v0.4** (Story, Highest, 5 pts, SH Sprint 3, Adrien Cubilla, Done)

> As the vision team, we need real insect appearance in detector training without drawing boxes by hand so that real wasps and bees stop being called hornets.

Acceptance criteria:

1. Given the Blender plus ControlNet proposal, when each step is checked against our evidence, hardware and FOSS rule, then the decision and its reasons are recorded in ADR-0010
2. Given iNaturalist pools that share no photo and no observation with tier P, when YOLOE labels them, then each kept photo has the iNaturalist species as class and its license and source recorded (result: 2,333 of 3,900 photos, 2,410 boxes)
3. Given a visual check of 15 random auto-labeled photos, when reviewed, then the label noise is reported in the results document (2 wrong, 1 partial, 2 photos with unboxed insects)
4. Given v0.4 trained with the v0.2 recipe on v0.2 scenes plus the photos, when evaluated, then tier S does not drop against v0.2 and tier P is reported on calib, then on the test split once (result: test accuracy 0.728 against 0.433, hornet P/R 0.68/0.83)
5. Given the release, when published under models/v0.4, then it has a model card, checksums and the attribution list of every real photo used

Design: [docs/adr/0010-real-photos-with-automatic-labels.md](../../docs/adr/0010-real-photos-with-automatic-labels.md), [docs/03-vision/07-results.md](../../docs/03-vision/07-results.md), [models/v0.4/MODEL_CARD.md](../../models/v0.4/MODEL_CARD.md)

Evidence: [vision/pseudolabel.py](../../vision/pseudolabel.py), [docs/03-vision/07-results.md](../../docs/03-vision/07-results.md), [models/v0.4/MODEL_CARD.md](../../models/v0.4/MODEL_CARD.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-13.1 ADR-0010: review the 3D rendering and diffusion proposal | Adrien Cubilla | 2 | Done |
| EN-13.2 pseudolabel.py: YOLOE boxes, iNaturalist classes, observation-level exclusion of tier P | Adrien Cubilla | 2 | Done |
| EN-13.3 Label 3,900 pool photos and audit a random sample | Adrien Cubilla | 1 | Done |
| EN-13.4 Train v0.4 (30 epochs, CPU) and evaluate tiers S and P | Adrien Cubilla | 3 | Done |
| EN-13.5 Fix ncnn input buffer lifetime in the node pipeline; add a determinism self-check | Adrien Cubilla | 2 | Done |
| EN-13.6 Package release v0.4, model card, attribution; update results | Adrien Cubilla | 2 | Done |

### EN-14

**Real-photo data v2 (iNaturalist 2026 snapshot, tier P v2, Open Images)** (Story, Highest, 8 pts, SH Sprint 3, Adrien Cubilla, Done)

> As the vision team, we need many more real photos of hornets and of what looks like them, and a real-photo test that shares no photographer with training, so that real-world numbers can be trusted.

Acceptance criteria:

1. Given the 2026-09-27 iNaturalist snapshot (36 GB), when streamed and filtered without storing it, then research-grade CC0/CC BY first photos of 27 taxon groups are indexed with observer, date and position (result: 743,462 photos)
2. Given that index, when tier P v2 is built, then photographers are hashed into test, calibration and training buckets, no photographer is on two sides, and test holds at least 450 hornets and 600 look-alike insects in named groups (result: 500 bee, 477 hornet, 635 look-alikes in 23 groups)
3. Given Open Images V7, when bee boxes are filtered, then only photos whose bees are boxed one by one are kept, with author and license per photo (result: 2,896 photos, 5,267 boxes)

Design: [docs/04-data/01-data-problem-and-strategy.md](../../docs/04-data/01-data-problem-and-strategy.md), [docs/03-vision/05-training-and-evaluation.md](../../docs/03-vision/05-training-and-evaluation.md)

Evidence: [vision/inat.py](../../vision/inat.py), [vision/openimages.py](../../vision/openimages.py), [vision/splits/P-inat-v2.tsv](../../vision/splits/P-inat-v2.tsv)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-14.1 Probe reachable hosts; choose snapshot and Open Images | Adrien Cubilla | 1 | Done |
| EN-14.2 inat.py: header-based streaming filter, 27 groups, most specific ancestor | Adrien Cubilla | 3 | Done |
| EN-14.3 inat.py v2: photographer buckets, quotas per group, parallel download with checksums | Adrien Cubilla | 3 | Done |
| EN-14.4 openimages.py: individually boxed bees, credits per photo | Adrien Cubilla | 2 | Done |

### EN-15

**Automatic labeling with OSI-licensed weights only, scored against human boxes** (Story, Highest, 5 pts, SH Sprint 3, Adrien Cubilla, Done)

> As the vision team, we need automatic boxes made only with OSI-licensed models, and a measured error rate, so that the training data respects the FOSS rule and its quality is known.

Acceptance criteria:

1. Given that YOLOE text prompts load Apple's research-only MobileCLIP weights, when the labeling pipeline is reviewed, then ADR-0011 records the finding and no code calls text prompts
2. Given prompt-free YOLOE proposals and an insectness classifier trained on Open Images human boxes, when scored on held-out Open Images photos, then precision and recall at IoU 0.5 are reported per threshold (result: 0.65 / 0.65 at insect probability 0.7)
3. Given the 13,090-photo training pool, when labeled and tidied, then a visual audit is recorded (result: 10,783 photos, 12,732 boxes; 6,497 SAM 2.1 cutouts)

Design: [docs/adr/0011-osi-clean-automatic-labeling.md](../../docs/adr/0011-osi-clean-automatic-labeling.md), [docs/03-vision/03-synthetic-image-pipeline.md](../../docs/03-vision/03-synthetic-image-pipeline.md)

Evidence: [vision/labeler.py](../../vision/labeler.py), [vision/insectness.py](../../vision/insectness.py), [vision/pseudolabel.py](../../vision/pseudolabel.py), [simulation/images/cutouts.py](../../simulation/images/cutouts.py)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-15.1 Check MobileCLIP license; ADR-0011; delete the weights | Adrien Cubilla | 1 | Done |
| EN-15.2 Benchmark prompt-free YOLOE sizes against Open Images boxes | Adrien Cubilla | 2 | Done |
| EN-15.3 Insectness classifier v1, then v2 with partial-box negatives | Adrien Cubilla | 3 | Done |
| EN-15.4 Label the pool, audit, tidy rule, relabel; cutouts v3; real mosaics | Adrien Cubilla | 4 | Done |

### EN-16

**Species verifier (stage 1b) for hornet and other-insect detections** (Story, Highest, 5 pts, SH Sprint 3, Adrien Cubilla, Done)

> As a beekeeper, I want a hornet alert to mean a hornet, not a wasp or a hoverfly, so that I act on alerts instead of ignoring them.

Acceptance criteria:

1. Given real crops of hornets and look-alikes plus synthetic top-down crops, when a 160 px YOLO26n-cls is trained, then top-1 on held-out photographers is reported (result: 0.922)
2. Given the unchanged v0.4 detector on tier P v2 calibration, when the verifier re-checks hornet and other-insect detections, then hornet precision rises above the 0.70 target (result: 0.566 to 0.903; look-alikes called hornet 133 to 20)
3. Given the v0.5 detector, when the two verifier thresholds are chosen on calibration as the most accurate pair with hornet recall >= 0.90 and precision >= 0.70, then they become the pipeline defaults (result: vth 0.2, flip 0.6)
4. Given the node pipeline, when the verifier runs in ncnn, then its probabilities match PyTorch and the rule is the same code as the evaluation (decide())
5. Given Open Images Bee photos, when the verifier checks them, then only honeybees are kept for training (result: 609 of 2,631; the rest were bumblebees, hoverflies, wasps and other bees)

Design: [docs/03-vision/04-model-architecture.md](../../docs/03-vision/04-model-architecture.md)

Evidence: [vision/verifier.py](../../vision/verifier.py), [vision/pipeline.py](../../vision/pipeline.py)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-16.1 Verifier dataset: real crops by photographer bucket, synthetic crops | Adrien Cubilla | 2 | Done |
| EN-16.2 Train, export to ncnn, compare with PyTorch | Adrien Cubilla | 2 | Done |
| EN-16.3 decide() rule in pipeline and eval_real; threshold sweep on calib | Adrien Cubilla | 2 | Done |
| EN-16.4 Open Images honeybee filter | Adrien Cubilla | 1 | Done |

### EN-17

**Vision iteration v0.5 (YOLO26n detector, clean data, release v0.5)** (Story, Highest, 8 pts, SH Sprint 3, Adrien Cubilla, Done)

> As the vision team, we need a detector trained on the larger, cleaner real data and a release that beats v0.4 on the new photographer-disjoint test.

Acceptance criteria:

1. Given synthetic scenes with cutouts v3, auto-labeled photos, real mosaics and verified Open Images bees, when YOLO26n is trained at 320 px, then tier S and tier P v2 calibration are compared with v0.4 (result: calibration accuracy 0.644 to 0.883 with the verifier)
2. Given a drop on synthetic entrance scenes, when a second synthetic set is added and the detector fine-tuned (v0.5b), then the choice between v0.5 and v0.5b is made on calibration and tier S only, before the test is opened (result: v0.5b)
3. Given the verifier, when detector thresholds are lowered on synthetic seed 8, then tier S hornet and beetle recall rise without a hornet precision below 0.95 (result: bee 0.25, hornet 0.30, beetle 0.35)
4. Given the chosen models, when tier P v2 test and tier P v1 test are opened once, then the numbers are reported next to v0.4 with the look-alike groups (result: 0.886 vs 0.652; hornet P/R 0.899/0.893 vs 0.570/0.748; look-alikes called hornet 34 vs 210; P v1 0.862 vs 0.728)
5. Given the release, when published under models/v0.5, then it has a model card, checksums, attribution of all 11,392 real photos and the Pi 3B latency estimate including stage 1b (result: 251 ms detector, 46 ms per verifier crop, 33 ms per bee, 173 MB)

Design: [docs/03-vision/07-results.md](../../docs/03-vision/07-results.md), [models/v0.5/MODEL_CARD.md](../../models/v0.5/MODEL_CARD.md)

Evidence: [models/v0.5/MODEL_CARD.md](../../models/v0.5/MODEL_CARD.md), [docs/03-vision/07-results.md](../../docs/03-vision/07-results.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-17.1 Compose v0.5 scenes with cutouts v3 | Adrien Cubilla | 1 | Done |
| EN-17.2 Train YOLO26n detector and YOLO26n-cls stage 2 | Adrien Cubilla | 3 | Done |
| EN-17.3 Second synthetic set and fine-tune (v0.5b); stage 2 choice at realistic prevalence | Adrien Cubilla | 2 | Done |
| EN-17.4 Detector thresholds on seed 8; verifier thresholds on calibration | Diego Alejandro Vasquez | 2 | Done |
| EN-17.5 Evaluate tiers S, P v1, P v2; latency; memory; release; results document | Adrien Cubilla | 4 | Done |

### EN-12

**Vision iteration v0.6 (real backgrounds, 416 px trial, Varroa threshold)** (Story, High, 8 pts, SH Sprint 5, Adrien Cubilla, To Do)

> As the vision team, we need the detector trained on our own board and checked at the camera's real scale so that the field test starts from entrance-domain numbers.

Acceptance criteria:

1. Given 50 or more empty-board frames from the mounted camera (tier C), when used as backgrounds, then the generator places insects on them with the camera's measured px/mm
2. Given stage 1 at 416 px, when compared with 320 px, then beetle recall (tier S) and the estimated Pi 3B latency are both reported, and 416 px is kept only if stage 1 stays under 1.0 s
3. Given stage 2, when its threshold is re-tuned on crops at 2 to 5 % Varroa prevalence, then precision and recall at that prevalence are reported
4. Given team captures of real bees at the entrance (tier C), when labeled, then the detector and verifier are scored on them

Blocked by: [HW-01](#hw-01)

Design: [docs/03-vision/07-results.md](../../docs/03-vision/07-results.md), [docs/03-vision/05-training-and-evaluation.md](../../docs/03-vision/05-training-and-evaluation.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-12.1 Capture empty-board backgrounds with the mounted camera | Ricardo Villarreal | 2 | To Do |
| EN-12.2 Generator: tier C backgrounds | Adrien Cubilla | 4 | To Do |
| EN-12.3 416 px trial; estimate latency | Adrien Cubilla | 4 | To Do |
| EN-12.4 Varroa threshold at realistic prevalence | Diego Alejandro Vasquez | 3 | To Do |
| EN-12.5 Label 200 tier C frames and score detector and verifier | Adrien Cubilla | 4 | To Do |

## E6 Backend platform & DevOps

Enablers for every user-facing story: message contract, Compose stack, database, CI.

Owner: James Tack. Component: `backend`.

| ID | Type | Summary | Pts | Sprint | Assignee | Status |
|---|---|---|---|---|---|---|
| [EN-07](#en-07) | Story | Freeze messaging contract v1 (JSON Schemas + contract tests) | 5 | Sprint 4 | Karen Jimenez | In Progress |
| [EN-08](#en-08) | Story | Docker Compose stack v1 (broker, database, API) | 5 | Sprint 4 | Maria de los Angeles Agudelo | Done |
| [EN-09](#en-09) | Task | CI pipeline (lint, tests, contracts) | 3 | Sprint 4 | Maria de los Angeles Agudelo | Done |

### EN-07

**Freeze messaging contract v1 (JSON Schemas + contract tests)** (Story, Highest, 5 pts, SH Sprint 4, Karen Jimenez, In Progress)

> As every team, we need the MQTT payloads frozen as JSON Schemas so that node, simulator and backend can be built in parallel.

Acceptance criteria:

1. Given infra/contracts, when CI runs, then every example in the messaging contract doc validates
2. Given a schema change, when a PR is opened, then both contract owners must approve

Design: [docs/05-backend/04-messaging-contract.md](../../docs/05-backend/04-messaging-contract.md)

Evidence: [infra/contracts](../../infra/contracts), [backend/src/smarthive/contracts](../../backend/src/smarthive/contracts)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-07.1 Schemas: telemetry, event, summary, health, status, config, cmd | Karen Jimenez | 5 | Done |
| EN-07.2 Generated Pydantic models and CI validation job | James Tack | 3 | Done |

### EN-08

**Docker Compose stack v1 (broker, database, API)** (Story, Highest, 5 pts, SH Sprint 4, Maria de los Angeles Agudelo, Done)

> As developers, we need one command that starts the server side so that everyone runs the same stack.

Acceptance criteria:

1. Given infra/compose.yaml, when docker compose --profile dev up runs, then Mosquitto (TLS), PostgreSQL with TimescaleDB (Apache-2.0 build), the API and Mailpit start healthy

Design: [docs/05-backend/08-deployment-and-operations.md](../../docs/05-backend/08-deployment-and-operations.md)

Evidence: [infra/compose.yaml](../../infra/compose.yaml), [backend/src/smarthive/db/migrations](../../backend/src/smarthive/db/migrations)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-08.1 Compose file with profiles and health checks | Maria de los Angeles Agudelo | 4 | Done |
| EN-08.2 Alembic baseline migration from the data model | James Tack | 4 | Done |

### EN-09

**CI pipeline (lint, tests, contracts)** (Task, High, 3 pts, SH Sprint 4, Maria de los Angeles Agudelo, Done)

> As developers, we need CI on every pull request so that main always works.

Acceptance criteria:

1. Given a pull request, when CI runs, then ruff, pytest (simulation tests included) and contract validation must pass
2. Given backlog.yaml, when it changes, then CI fails unless the generated Jira files were rebuilt

Design: [docs/05-backend/08-deployment-and-operations.md](../../docs/05-backend/08-deployment-and-operations.md)

Evidence: [.github/workflows/tests.yml](../../.github/workflows/tests.yml)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| EN-09.1 GitHub Actions workflow: simulation tests, pipeline self-check, Jira build check (green) | Maria de los Angeles Agudelo | 3 | Done |
| EN-09.2 Add ruff lint and format check | Maria de los Angeles Agudelo | 1 | Done |
| EN-09.3 Add contract validation once infra/contracts exists (EN-07) | Karen Jimenez | 1 | Done |

## E7 Project foundations

Requirements, architecture, decisions, documentation and the client interview.

Owner: Adrien Cubilla. Component: `docs`.

| ID | Type | Summary | Pts | Sprint | Assignee | Status |
|---|---|---|---|---|---|---|
| [PM-01](#pm-01) | Task | Repository structure, contribution rules and documentation set | 5 | Sprint 3 | Adrien Cubilla | Done |
| [PM-02](#pm-02) | Task | Architecture decision records 0001 to 0008 | 3 | Sprint 3 | James Tack | Done |
| [PM-03](#pm-03) | Task | Client interview with the 30 elicitation questions | 3 | Sprint 4 | Adrien Cubilla | To Do |
| [PM-04](#pm-04) | Task | Align presentation and spreadsheet backlog with the Pi 3B design | 1 | Sprint 4 | Ricardo Villarreal | To Do |
| [PM-05](#pm-05) | Task | Final demo and evaluation report per data tier | 8 | Sprint 10 | Adrien Cubilla | To Do |

### PM-01

**Repository structure, contribution rules and documentation set** (Task, High, 5 pts, SH Sprint 3, Adrien Cubilla, Done)

> As a team, we need one organized repository with the project's documentation in English so that everyone works from the same plan.

Acceptance criteria:

1. Given the repository, when a new member opens the README, then they find the overview, team, architecture diagram, repo map and roadmap
2. Given the team's source documents (plan, design, epics, elicitation, proposal, backlog), when they are migrated, then each lives in docs/ in English and contradictions are flagged
3. Given a pull request, when it is opened, then a template asks for area, contract impact, tests and data provenance

Design: [README.md](../../README.md), [CONTRIBUTING.md](../../CONTRIBUTING.md), [docs/README.md](../../docs/README.md)

Evidence: [docs/README.md](../../docs/README.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| PM-01.1 Translate and migrate design document, epics, elicitation matrix | Adrien Cubilla | 6 | Done |
| PM-01.2 README, CONTRIBUTING, issue and PR templates | Maria de los Angeles Agudelo | 3 | Done |
| PM-01.3 Docs index, glossary, risk register, way of working | Diego Alejandro Vasquez | 3 | Done |

### PM-02

**Architecture decision records 0001 to 0008** (Task, High, 3 pts, SH Sprint 3, James Tack, Done)

> As a team, we need our expensive-to-reverse decisions written down with alternatives so that nobody reopens them by accident.

Acceptance criteria:

1. Given each major decision (synthetic data, Pi 3B, MQTT, PostgreSQL/TimescaleDB, modular monolith, image storage, detector license), when reviewing docs/adr, then an ADR states context, decision, alternatives and consequences

Design: [docs/adr/README.md](../../docs/adr/README.md)

Evidence: [docs/adr/README.md](../../docs/adr/README.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| PM-02.1 Write ADR-0001 to ADR-0007 | James Tack | 4 | Done |
| PM-02.2 Decide ADR-0008 (detector framework and repository license) with benchmark numbers | Adrien Cubilla | 2 | Done |

### PM-03

**Client interview with the 30 elicitation questions** (Task, Highest, 3 pts, SH Sprint 4, Adrien Cubilla, To Do)

> As the product owner, I need the client's answers to the elicitation matrix so that working assumptions become requirements.

Acceptance criteria:

1. Given the interview, when it ends, then every EL-xx row has an answer or an explicit 'client does not know'
2. Given an answer that contradicts a working assumption, when the log is filled, then the affected document or ADR is updated in the same sprint

Design: [docs/01-requirements/elicitation-matrix.md](../../docs/01-requirements/elicitation-matrix.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| PM-03.1 Schedule the meeting and send the question list in advance | Adrien Cubilla | 1 | To Do |
| PM-03.2 Run the interview and fill the interview log | Adrien Cubilla | 3 | To Do |
| PM-03.3 Propagate answers to docs (thresholds, retention, channels, demo scope) | Diego Alejandro Vasquez | 3 | To Do |

### PM-04

**Align presentation and spreadsheet backlog with the Pi 3B design** (Task, Medium, 1 pts, SH Sprint 4, Ricardo Villarreal, To Do)

> As a team, we need the presentation and backlog to describe the same node as the electrical design so that reviewers are not confused.

Acceptance criteria:

1. Given the presentation and the spreadsheet backlog, when they are reviewed, then they mention the Raspberry Pi 3B + Ethernet node of Prototype 1 and list ESP32/LoRaWAN only as a future option (ADR-0003)

Design: [docs/02-hardware/hardware-review-notes.md](../../docs/02-hardware/hardware-review-notes.md), [docs/adr/0003-raspberry-pi-3b-edge-node.md](../../docs/adr/0003-raspberry-pi-3b-edge-node.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| PM-04.1 Update slides 8 and 9 (system design, technologies) | Ricardo Villarreal | 1 | To Do |
| PM-04.2 Renumber spreadsheet stories to US01-US22 and add EN items | Diego Alejandro Vasquez | 1 | To Do |

### PM-05

**Final demo and evaluation report per data tier** (Task, Highest, 8 pts, SH Sprint 10, Adrien Cubilla, To Do)

> As the team, we need a demo script and a report that states what works on synthetic, public and field data so that the evaluation is honest.

Acceptance criteria:

1. Given the report, when read, then every metric names its tier (S, P, C, F) and the domain gap is stated
2. Given the demo, when run, then node (or simulator) to server to dashboard to alert works live

Design: [docs/03-vision/07-results.md](../../docs/03-vision/07-results.md)

| Sub-task | Assignee | Hours | Status |
|---|---|---|---|
| PM-05.1 Demo script and demo_day scenario rehearsal | Maria de los Angeles Agudelo | 4 | To Do |
| PM-05.2 Evaluation report (vision, telemetry models) | Adrien Cubilla | 6 | To Do |
| PM-05.3 Time-series results section | Diego Alejandro Vasquez | 3 | To Do |
