# ADR-0008: Detector framework and repository license

Status: Proposed, needs a team decision
Date: 2026-10-06
Deciders: whole team (license), Adrien Cubilla (framework)

## Context

The vision proposal names YOLOv8-nano as the first candidate. Ultralytics YOLO (v8, 11 and later) is licensed under AGPL-3.0. That is an OSI-approved open-source license, so it meets our FOSS rule, but it is strong copyleft with a network clause: if we use it, the code that uses it, the training and inference scripts and the trained weights must be released under AGPL-3.0 when we distribute the system or offer it over a network. A closed or permissive-licensed version of SmartHive would need a commercial license.

Apache-2.0 alternatives that fit a Raspberry Pi 3B exist: NanoDet-Plus and YOLOX-Nano.

The repository has no license yet.

## Options

| Option | Repository license | Detector | Effect |
|---|---|---|---|
| A | AGPL-3.0 for the whole repository | Ultralytics YOLO11n / YOLOv8n | Fastest iteration; everything we publish is AGPL; anyone building on SmartHive must keep it open |
| B | Apache-2.0 or MIT | NanoDet-Plus or YOLOX | Permissive; more work on training tooling and export |
| C | Apache-2.0 for everything except `vision/` (AGPL-3.0) | Ultralytics for experiments, NanoDet-Plus for what ships on the node | Keeps the deployable system permissive while using the best tooling for research; needs care to keep the boundary clean |

## Recommendation

Train both candidates in the benchmark spike (EN-06) and decide with the numbers. If Ultralytics is clearly better on the Pi, choose option A: the project is an open academic demonstrator, and AGPL-3.0 matches that. If the difference is small, choose option B for simplicity.

## Consequences

Whichever option is chosen, add a `LICENSE` file at the root, mention the license in the README, and record the licenses of datasets and assets separately (they are not covered by the code license).
