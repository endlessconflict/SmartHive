# ADR-0008: Detector framework and repository license

Status: Accepted
Date: 2026-10-06
Deciders: whole team (license), Adrien Cubilla (framework)

## Context

The vision proposal named YOLOv8-nano as the first candidate. Ultralytics YOLO (v8, 11 and later) is licensed under AGPL-3.0. That is an OSI-approved open-source license, so it meets our FOSS rule. It is also strong copyleft with a network clause: the code that uses it, the training and inference scripts and the trained weights must be released under AGPL-3.0 when the system is distributed or offered over a network. A closed or permissively licensed SmartHive would need a commercial license.

Apache-2.0 alternatives that fit a Raspberry Pi 3B exist: NanoDet-Plus and YOLOX-Nano.

What matters for us, in order:

1. Runs on a Raspberry Pi 3B (1 GB, Cortex-A53, no accelerator) within about a second per frame.
2. Can be trained on a 4-core laptop CPU, with no GPU and no budget.
3. Gets from training to an ncnn model on the node without hand-written conversion code.
4. A license compatible with an open academic project.

## Options

| Option | Repository license | Detector | Effect |
|---|---|---|---|
| A | AGPL-3.0 for the whole repository | Ultralytics YOLO11n (detector) and YOLO11n-cls (Varroa classifier) | One toolchain for both stages; CPU training and ncnn export work out of the box; everything we publish is AGPL |
| B | Apache-2.0 or MIT | NanoDet-Plus or YOLOX | Permissive; NanoDet-Plus is cheaper per frame, but its training code pins old library versions, and stage 2 needs a second toolchain |
| C | Apache-2.0 except `vision/` (AGPL-3.0) | Ultralytics for research, NanoDet-Plus on the node | Two toolchains and a license boundary to police |

## Decision

**Option A.** Ultralytics YOLO11 for both stages, trained on CPU with COCO/ImageNet-pretrained weights, exported to ncnn, and run on the node through the ncnn Python bindings only. Ultralytics and torch are never installed on the Pi. The repository is licensed AGPL-3.0 ([LICENSE](../../LICENSE)).

Why:

- One training and export path for both stages. `vision/train.py` and `vision/export.py` are thin wrappers, which matters with one vision person on the team.
- The Pi 3B estimate for YOLO11n at 320 px is within the latency budget (numbers in [results](../03-vision/07-results.md), anchored to ncnn's published Raspberry Pi 3 measurements). NanoDet-m is cheaper, but the gap does not justify a second toolchain while we are inside the budget.
- SmartHive is an open academic demonstrator. AGPL-3.0 keeps it open and costs us nothing.

## When to revisit

- The on-device benchmark (Jira US11) misses the budget even with motion gating: try YOLO11 at 256 px or a narrower custom scale first (same toolchain), then NanoDet-Plus.
- The project ever needs a closed or commercial version: switch to option B or buy an Ultralytics license. The two-stage pipeline in `vision/pipeline.py` only assumes "a detector with a YOLO-style output and a classifier", so the node code barely changes.

## Consequences

- `LICENSE` is AGPL-3.0. Contributors license their contributions under it.
- Dataset and asset licenses are separate from the code license and are recorded with the data (the synthetic datasets have no third-party content, see [ADR-0009](0009-procedural-insect-rendering.md)).
