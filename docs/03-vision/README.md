# Vision: pest and threat detection

Status: implemented; five iterations, v0.5 released ([model card](../../models/v0.5/MODEL_CARD.md)). Results: [07-results.md](07-results.md)

Owner: Adrien Cubilla. Hardware side with Ricardo Villarreal.

## Summary

A camera on the node watches the landing board. A cheap motion check decides which frames are worth analyzing. On those, a small detector finds bees, hornets, small hive beetles and other insects at low resolution. Each bee is then cropped from the full-resolution frame and passed to a tiny classifier that answers one question: is there a Varroa mite on it? Detections are aggregated over several frames before anything becomes an alert, and only frames with something relevant are kept.

All of it is trained on synthetic images, because there is no client data. Every insect in those images is drawn by a procedural renderer at its real size in millimeters, on procedural landing boards, with physically motivated placement, shadows, lighting, blur and camera noise, so the training data carries no third-party license. Real, openly licensed photos from the iNaturalist Open Dataset are kept apart and used only to measure how well this transfers to real insects.

```mermaid
flowchart LR
    CAM[Camera<br/>full res + low res streams] --> MG{Motion?}
    MG -- no --> DROP[Discard frame]
    MG -- yes --> S1[Stage 1 detector<br/>320-416 px<br/>bee, hornet, shb, other]
    S1 --> CROP[Crop each bee<br/>from full-res frame]
    CROP --> S2[Stage 2 classifier<br/>128 px<br/>varroa yes/no]
    S1 --> AGG[Temporal aggregation<br/>k of n frames]
    S2 --> AGG
    AGG --> EV[Detection events<br/>+ relevant images]
```

## Reading order

| # | Document | Content |
|---|---|---|
| 1 | [Problem framing](01-problem-framing.md) | Classes, sizes, what the camera can and cannot see, output definition |
| 2 | [Camera and optics](02-camera-and-optics.md) | Resolution math, camera requirements, mounting |
| 3 | [Synthetic image pipeline](03-synthetic-image-pipeline.md) | Procedural renderer, boards, placement, labels, camera model |
| 4 | [Model architecture](04-model-architecture.md) | Two-stage design for a Pi 3B, model candidates, licenses |
| 5 | [Training and evaluation](05-training-and-evaluation.md) | Splits, metrics, sim-to-real protocol, acceptance criteria |
| 6 | [Edge deployment](06-edge-deployment.md) | Runtime pipeline, export to NCNN, benchmarks to run |
| 7 | [Results](07-results.md) | What v0.1 to v0.5 achieve per data tier, why v0.5 is the release, and what v0.6 changes |

## Main decisions

| Decision | Where |
|---|---|
| Synthetic-first training data | [ADR-0002](../adr/0002-synthetic-first-training-data.md) |
| Inference on a Raspberry Pi 3B | [ADR-0003](../adr/0003-raspberry-pi-3b-edge-node.md) |
| Detector family and licensing (Ultralytics AGPL vs Apache-2.0 alternatives) | [ADR-0008](../adr/0008-detector-licensing.md) |
| Procedural insects instead of photo cutouts | [ADR-0009](../adr/0009-procedural-insect-rendering.md) |

## Origin

This folder expands the "Pest and Threat Detection Model" proposal written for the project. The proposal's methodology (object detection, YOLOv8-nano as a first candidate, transfer learning, recall-first evaluation, domain gap analysis, edge deployment, later fusion with sensor data) is kept. What changed: the data acquisition stage is now a synthetic data pipeline, and the model is split into two stages because of the resolution problem explained in [camera and optics](02-camera-and-optics.md).
