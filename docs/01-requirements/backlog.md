# Product backlog

Status: Historical. The working backlog now lives in [docs/jira](../jira/README.md) (epics, stories, sub-tasks, estimates, sprints, ready for Jira). This page keeps the rows recovered from the original spreadsheet and how they map.

The team backlog lives in a spreadsheet ("Smarthive- BACKLOG.xlsx") with four sheets: *Product backlog - Initial*, *Product backlog - Sprint 2 (after)*, *Product backlog - Sprint 3 (after)* and *Dropdown menus*. The copy available while writing these docs was a PDF export of the first screen, so only the first rows could be read. They are reproduced below.

| Spreadsheet ID | User story | Requirement | Maps to |
|---|---|---|---|
| US1 | As a team, we need to define the bill of materials (BOM) and buy the node components (ESP32, HX711 + load cell, temperature/humidity sensor, microphone, camera) so that we can build the prototype. | R1 | Hardware task; no epic story |
| US2 | As a beekeeper, I need the node to measure the hive weight with the load cell and HX711 so that I can track nectar accumulation. | R1 | US02 |
| US3 | As a beekeeper, I need to measure internal temperature and humidity (brood nest and honey super zones) so that I know the hive's internal climate. | R2 | US01 |
| US4 | As a beekeeper, I need the node to send its readings over MQTT with TLS to the cloud... (cut off in the export) | | US04, US05 |

## Things to fix in the spreadsheet

1. Two numbering schemes exist (`US1` in the spreadsheet, `US01` in the epics document). Use the epics numbering everywhere and keep the old ID in a column, as in the table above.
2. The BOM story lists an ESP32 and a microphone. The current electrical design uses a Raspberry Pi 3B and has no microphone. See [hardware review notes](../02-hardware/hardware-review-notes.md#1-two-different-node-designs-are-in-circulation).
3. Add the work that the synthetic data decision created. These enablers are now in the Jira backlog with full detail (EN-03 became the procedural renderer, and EN-06 the DVC setup; the benchmark spike is part of US11):

| Proposed ID | Item | Unblocks |
|---|---|---|
| EN-01 | Hive telemetry simulator v1 (temperature, humidity, weight, events) | US13, US16, US18 to US22 |
| EN-02 | Simulator MQTT replay (fake nodes) | US05, US06, US12, all dashboard work |
| EN-03 | Asset library and manifest for synthetic images | US09, US10 |
| EN-04 | Synthetic entrance image compositor v1 | US09, US10 |
| EN-05 | Real-image validation set (public data, license-checked) | Honest evaluation of US09, US10 |
| EN-06 | Pi 3B inference benchmark spike | US11 |
| EN-07 | MQTT contract v1 frozen + JSON Schemas + contract tests | US04, US05 |
| EN-08 | Docker Compose stack v1 (broker, database, API) | Everything server-side |

Once the full spreadsheet is exported (File → Download → CSV for each sheet), replace this page with the complete list or link the GitHub Project board.
