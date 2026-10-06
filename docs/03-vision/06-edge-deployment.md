# Edge deployment

Status: Proposed

Owners: Adrien Cubilla (vision service), Ricardo Villarreal (OS image, camera, power)

How the vision models run on the Raspberry Pi 3B. The other services on the node (sensors, uplink, agent) are described in [edge node software](../05-backend/03-edge-node-software.md).

## Runtime pipeline

```mermaid
sequenceDiagram
    participant CAM as camd
    participant VIS as visiond
    participant DB as outbox (SQLite)
    participant FS as image folder
    loop every 0.5 s (configurable)
        CAM->>CAM: grab low-res frame (e.g. 320×240 YUV)
        CAM->>CAM: motion score vs background model
        alt motion above threshold and visiond idle
            CAM->>CAM: capture full-res still (same instant, second stream)
            CAM->>VIS: frame handle (shared memory / file in tmpfs)
            VIS->>VIS: stage 1 on 320 px
            VIS->>VIS: crop sharp bees, stage 2 on 128 px
            VIS->>VIS: update k-of-n windows and varroa counters
            VIS->>DB: frame record (summary)
            opt something relevant (threat or varroa positive or periodic sample)
                VIS->>FS: save JPEG (full frame + crops)
                VIS->>DB: image record, pending upload
            end
            opt aggregation rule fires
                VIS->>DB: detection event, pending publish
            end
        end
    end
```

Key points:

- Two camera streams. With a CSI camera and `picamera2`, the low-resolution stream for motion and the full-resolution stream for stills come from the same sensor at the same time, with no extra resize on the CPU. With a USB camera, use V4L2 at a moderate resolution and grab stills on demand; it costs more CPU.
- Motion gating. OpenCV background subtraction (MOG2) or a running-average difference on the low-res stream. The detector runs only on frames with motion and only when it is not already busy (frames are dropped, not queued, so latency never piles up).
- Night mode. Between configured sunset and sunrise, the camera stops entirely.
- Relevant images only (US08). Full frames are kept when a threat or a Varroa-positive bee is found, plus one periodic sample per hour for the dashboard's "latest image" (US15) and for future field evaluation.
- Frames live in RAM. Candidate frames go through `tmpfs` (`/run/smarthive/frames`) so the SD card only sees the images we keep.

## Runtime and libraries on the node

| Component | Choice | License | Why |
|---|---|---|---|
| OS | Raspberry Pi OS Lite, 64-bit | Various FOSS | Headless; 64-bit gives NEON-friendly AArch64 builds |
| Camera | `picamera2` (CSI) or OpenCV V4L2 (USB) | BSD-2 / Apache-2.0 | |
| Image ops | OpenCV (headless build), NumPy | Apache-2.0 / BSD | |
| Inference | NCNN Python bindings | BSD-3 | Fastest CPU runtime on ARM in published comparisons; small footprint |
| Fallback inference | ONNX Runtime | MIT | If an operator is missing in NCNN |
| Not on the node | PyTorch, Ultralytics, TensorFlow | | Too heavy for 1 GB of RAM; used only for training and export |

## Export path

```mermaid
flowchart LR
    PT[PyTorch checkpoint<br/>training machine] --> ONNX[ONNX<br/>opset fixed]
    ONNX --> SIM[onnxsim<br/>simplify]
    SIM --> NC[NCNN param/bin<br/>FP32]
    NC --> Q[INT8 calibration<br/>200-500 images]
    Q --> PKG[Model package<br/>param, bin, meta.json]
    PKG --> NODE[Node: /opt/smarthive/models/]
```

`meta.json` holds the class names, input size, normalization, thresholds, model version and the dataset ID it was trained on. The vision service refuses to load a model whose metadata does not match the output contract version it implements.

## Memory budget (1 GB)

| Consumer | Budget |
|---|---|
| OS, systemd, networking, SSH | ~150 MB |
| `sensord`, `agentd`, `uplinkd` (Python) | ~120 MB together |
| `camd` (camera buffers, motion) | ~120 MB |
| `visiond` (NCNN, two models, buffers) | ≤ 250 MB |
| tmpfs for frames | 64 MB |
| GPU memory split (camera needs some) | 128 MB (`gpu_mem` in `config.txt`) |
| Free margin | the rest |

Each service has `MemoryMax=` in its systemd unit. If `visiond` exceeds it, the kernel kills it and systemd restarts it; the sensors keep running.

## Benchmark spike (EN-06)

Before committing to a model, run this on the real Pi 3B with the full node software active:

| # | Measurement | Variants |
|---|---|---|
| 1 | Stage 1 latency p50/p95 | YOLO11n vs NanoDet-Plus-m; 320 vs 416; FP32 vs INT8; NCNN threads 2/3/4 |
| 2 | Stage 2 latency per crop | MobileNetV3-Small vs custom CNN; 96 vs 128 px |
| 3 | Peak RSS | Same variants |
| 4 | SoC temperature after 30 min at a busy-entrance duty cycle | In the enclosure, in the sun if possible |
| 5 | Power draw | Idle, motion only, detector running |
| 6 | Camera CPU cost | CSI dual stream vs USB |

The script lives in `vision/bench/` and writes a JSON report that is committed alongside the decision.

## Updating models on the node

Version 1: copy the model package with `rsync` over SSH and restart `visiond`; the previous package is kept for rollback. Over-the-air updates for the whole node software (REQ-14) are planned in the [roadmap](../roadmap.md) and will reuse the same package format.
