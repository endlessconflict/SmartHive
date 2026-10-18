# Elicitation matrix

Status: Open. All 30 questions are still pending; the client meeting has not happened yet.

Translated from "Matriz de Elicitación Smart Hive". The original has four sheets: the matrix, base requirements, an interview log (empty) and an interview script. The script asks the same questions grouped into blocks A to F, so it is not repeated here.

## Working assumptions

We cannot stop work until the client answers. For each question, the last column gives the default the team will build against. Defaults are chosen to be cheap to change later. When the client answers, update the row, move the answer into the interview log below and check whether any document or ADR needs to change.

## Matrix

| ID | Area | Question | Impact | Priority | Working assumption until answered |
|---|---|---|---|---|---|
| EL-01 | Users and roles | Who will use the system and what can each type of user do? | User management, authorization, dashboard | High | Two roles: `beekeeper` (own hives) and `admin` (everything) |
| EL-02 | Hives and apiaries | Can a user manage several hives and apiaries? How is each hive identified? | Data model, API, dashboard | High | Yes. User → apiaries → hives. Hives have a UUID and a human name; nodes are assigned to hives over time |
| EL-03 | Hive data | What basic information must be recorded for a hive besides sensor readings? | Database, interfaces | High | Name, apiary, location, hive type, number of boxes, notes, install date |
| EL-04 | MVP scope | Which features are essential for the first version and which are optional? | Architecture, planning, deliverables | High | Priority 1 stories in the epics document |
| EL-05 | Data acquisition | How often should weight, temperature and humidity be measured? | Firmware, storage, communications | High | Every 60 s for temperature and humidity (DHT11 limit is about 1 Hz); weight every 5 min |
| EL-06 | Acoustics and images | How often and for how long should audio and images be captured? | Edge computing, bandwidth, storage | High | One frame every 2 s analyzed for motion; detector only on motion; full images kept only when relevant (US08) |
| EL-07 | Connectivity loss | What should happen when the node loses connection to the gateway or the cloud? | Local storage, sync, fault tolerance | High | Store and forward for at least 7 days; oldest-first upload on reconnection |
| EL-08 | Sensor failure | What should the system show or do when a sensor stops responding or gives invalid data? | Monitoring, alerts, validation | High | Readings carry a quality flag; three consecutive failures raise a `sensor_fault` warning |
| EL-09 | Data retention | How long should historical data and images be kept? | Database, storage, cost | Medium | Telemetry forever (it is small); images with detections 1 year; other images 30 days |
| EL-10 | Honey prediction | What exactly does "honey yield" mean: weight increase, kg produced, other? | ML model, dashboard, metrics | High | Net weight gain of the hive over the window, excluding management events |
| EL-11 | Recommendations | Should the recommendation to add supers or harvest be informative or raise an alert? | Rules engine, alerts | High | Informative (shown in dashboard, no notification) |
| EL-12 | Prediction confidence | What should happen when a prediction has low confidence? | AI, UX, alerts | Medium | Show the range; if the range is wider than a threshold, show "not enough data" |
| EL-13 | Swarming | The proposal says alert 24 to 48 h before swarming. Is that mandatory or a target? | Acoustic model, evaluation | High | A target, not a requirement. Detect swarming after the fact from weight first |
| EL-14 | Acoustic states | Are pre-swarming, normal and queenless the only states to distinguish? | Dataset, classification, UX | Medium | Yes, if acoustics is done at all (no microphone in Prototype 1) |
| EL-15 | Priority pests | Which threats are mandatory for the demo: Varroa, small hive beetle, Asian hornet, others? | Vision scope, dataset, demo | High | Varroa mandatory; hornet second; small hive beetle third |
| EL-16 | Detection confidence | From what confidence level is a visual detection valid? | Inference, alerts, false positives | High | Per-class thresholds tuned for recall; an alert needs k detections in n frames (see vision docs) |
| EL-17 | Alerts | Which events must raise an alert and which only appear in the dashboard? | Alert engine, notifications | High | See the [alert catalog](../05-backend/07-alerts-and-rules.md) |
| EL-18 | Recipients and channels | Who receives each alert? Can they choose between push, email and SMS? | Notifications, users | High | Owner of the hive; in-app and email; push via ntfy as an option; no SMS (it costs money) |
| EL-19 | Rule configuration | Can users create their own rules or only adjust predefined ones? | Dashboard, rules engine | Medium | Adjust thresholds of predefined rules only |
| EL-20 | Alert resolution | When is an alert considered attended, resolved or closed? | Database, UX, audit | Medium | `open` → `acknowledged` (user saw it) → `resolved` (user says it is handled, with a note) |
| EL-21 | Dashboard | What must appear on the main screen? | Frontend, API | High | Per hive: status, last reading, open alerts, last image |
| EL-22 | Real time | What does "real time" mean for the client, and what latency is acceptable? | Communications, backend, WebSocket/API | High | Under 10 s from measurement to dashboard on a working connection |
| EL-23 | History | Which variables, periods and filters should be available in historical charts? | Database, API, dashboard | Medium | All variables; last 24 h, 7 d, 30 d, custom; per hive |
| EL-24 | Export | Should hive, date range and variables be selectable when exporting CSV/JSON? | API, reports | Medium | Yes, all three |
| EL-25 | New anomalies | What should the system do when it detects an anomaly it cannot link to a known threat? | AI, alerts, UX | High | Warning in dashboard (US17), no notification |
| EL-26 | Model quality | What are the minimum acceptable values for MAE/RMSE and precision/recall/F1? | AI validation, deliverables | High | Proposed targets in the [vision evaluation doc](https://github.com/endlessconflict/SmartHive-Vision/blob/main/docs/05-training-and-evaluation.md#acceptance-criteria) |
| EL-27 | Platform | Is a native mobile app required, or is a responsive web app enough? | Frontend, deployment | Medium | Responsive web app |
| EL-28 | Security | Besides TLS for MQTT, which authentication, authorization and device management mechanisms are needed? | Security requirements | High | User passwords hashed with Argon2, short-lived tokens, per-device MQTT credentials with topic ACLs |
| EL-29 | Technology alternatives | The proposal mentions LoRaWAN/NB-IoT, ESP32/STM32 and InfluxDB/TimescaleDB. Is any of them mandatory? | Architecture, technology choice | High | None mandatory. Prototype 1 uses Raspberry Pi 3B + Ethernet + PostgreSQL/TimescaleDB (see ADRs) |
| EL-30 | Demo | Which features must work during the final demo? | Integration, tests, architecture | High | Live node (or simulator) → server → dashboard → alert on a detection |

## Base requirements

From the "Requisitos base" sheet. "State" is how well the requirement was defined when the sheet was written.

| ID | Area | Requirement | State | Still to clarify | Type |
|---|---|---|---|---|---|
| REQ-01 | Users | Beekeepers can monitor their hives remotely | Partial | User types, permissions, actions | Functional |
| REQ-02 | Monitoring | Capture weight, temperature, humidity, audio and images | Partial | Frequencies, durations, failure behavior | Functional |
| REQ-03 | Prediction | Predict daily and weekly honey yield | Defined | Exact metric and acceptance criteria | Functional |
| REQ-04 | Recommendations | Recommend when to add supers or harvest | Partial | Rules, confidence, whether it alerts | Functional |
| REQ-05 | Swarming | Detect pre-swarming acoustic patterns | Partial | Classes, metrics, validate 24 to 48 h target | Functional |
| REQ-06 | Pests | Detect pests and intruders with computer vision | Partial | Mandatory threats, confidence threshold | Functional |
| REQ-07 | Alerts | Configurable alerts over several channels | Partial | Events, recipients, severity, mandatory channels | Functional |
| REQ-08 | Dashboard | Show readings, status, trends and history | Partial | Content, filters, meaning of "real time" | Functional |
| REQ-09 | Export | Export logs as CSV and JSON | Defined | Filters and scope | Functional |
| REQ-10 | Anomalies | Detect anomalies not covered by the classifiers | Partial | Response to unknown anomalies | Functional |
| REQ-11 | Security | MQTT uses TLS | Defined | User and device authentication and authorization | Non-functional |
| REQ-12 | Availability | Remote monitoring is possible | Partial | Availability, latency, behavior when disconnected | Non-functional |
| REQ-13 | Data | The platform stores time series and sensor data | Defined | Retention, backup, raw data policy | Non-functional |
| REQ-14 | OTA | Firmware can be updated remotely | Defined | Authorization, rollback, update monitoring | Functional |
| REQ-15 | Prototype | At least one node installed on a real or simulated hive | Defined | Demo scenario | Constraint / deliverable |
| REQ-16 | Evaluation | Models report metrics on test data | Defined | Minimum acceptance thresholds | Non-functional |

## Interview log

Empty until the meeting. Use this format:

| Question ID | Client answer | Derived requirement | Type | Priority | Decision / pending | Architectural impact |
|---|---|---|---|---|---|---|
| | | | | | | |
