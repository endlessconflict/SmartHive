# SmartHive vision models v0.2

Two ncnn models for the entrance camera on the hive node: a detector (stage 1) and a Varroa crop classifier (stage 2). Released 2026-10-06. Full evaluation: [vision results](../../docs/03-vision/07-results.md).

## Files

| Path | What | Input | Output |
|---|---|---|---|
| `stage1/model.ncnn.{param,bin}` | YOLO11n detector, 2.59 M params, 1.6 GFLOPs | `in0`, 1×3×320×320, RGB, 0 to 1, letterboxed | `out0`, 8×2100 (4 box + 4 class scores) |
| `stage2/model.ncnn.{param,bin}` | YOLO11n-cls classifier, 2.81 M params, 0.13 GFLOPs | `in0`, 1×3×128×128, RGB, 0 to 1 | `out0`, 2 class probabilities |
| `*/metadata.yaml` | Class names and export settings from Ultralytics | | |
| `ATTRIBUTION.tsv` | Source, license and observer of each real photo used for training cutouts | | |
| `SHA256SUMS` | Checksums; check with `sha256sum -c SHA256SUMS` from this folder | | |

Classes: stage 1 `0 bee, 1 hornet, 2 shb, 3 other_insect`; stage 2 `0 clean, 1 varroa`.

Run them with [`vision/pipeline.py`](../../vision/pipeline.py), which needs only `numpy`, `opencv-python-headless` and `ncnn` ([`edge/requirements.txt`](../../edge/requirements.txt)):

```python
import cv2
from pathlib import Path
from vision.pipeline import Detector

det = Detector(Path("models/v0.2/stage1"), Path("models/v0.2/stage2"))
record = det(cv2.imread("frame.jpg"))  # full-resolution BGR frame
```

Operating thresholds: bee 0.35, hornet 0.45, shb 0.5, other_insect 0.5, varroa 0.6. Alerts use k-of-n aggregation (hornet 3 of 10 frames, beetle 2 of 10).

## Training data

Synthetic only (tier S), dataset `S-images-entrance-v0.2-s2`: 4,000 scenes at 1640×1232 from [`simulation/images/compose.py`](../../simulation/images/compose.py), seed 2.

- Insects: half procedurally drawn ([ADR-0009](../../docs/adr/0009-procedural-insect-rendering.md)), half cut out of 626 iNaturalist photos (234 bee, 245 hornet, 147 other insect; 297 CC0 and 329 CC BY photos). Cutouts were made with YOLOE text prompts and SAM 2.1 tiny.
- None of the cutout photos is in the frozen tier P evaluation split.
- Mites: drawn at physical scale (1.45 to 1.75 mm wide) on about 45 % of bees, including real-photo bees.
- Backgrounds: procedural boards, 15 % random textures.
- Stage 2 trains on crops cut from the full-resolution frames: 17,520 clean and 14,566 varroa.

Starting weights: Ultralytics `yolo11n.pt` (COCO) and `yolo11n-cls.pt` (ImageNet). Stage 1: 30 epochs at 320 px; stage 2: 12 epochs at 128 px. CPU only.

## Results

| Tier | Test | Result |
|---|---|---|
| S | Detector val, 600 scenes | mAP50 0.781, mAP50-95 0.437 |
| S | Stage 2 val, 5,577 crops | top-1 0.877 |
| S | Full ncnn pipeline, 200 fresh scenes | hornet P 1.00 / R 0.91 (96 % of hornet scenes); bee P 0.95 / R 0.92; Varroa on bees P 0.96 / R 0.92; beetle R 0.45 |
| P | iNaturalist test split, 600 photos, image-level | accuracy 0.433 (chance 0.333); hornet R 0.69 / P 0.43; bee R 0.57 / P 0.42; other insect R 0.05 |
| Edge | Raspberry Pi 3B, estimated from ncnn's published Pi timings | stage 1 ≈ 241 ms (162 to 455); stage 2 ≈ 34 ms per crop; peak memory 145 MB |

## Intended use

Research prototype for the SmartHive node: count bees, flag possible hornets and beetles, estimate the share of bees carrying a visible Varroa mite, at a top-down entrance camera.

## Limitations

- **Not validated on our camera.** No tier C or F data exists yet. Real-photo accuracy is measured on iNaturalist side views, which differ from the entrance view.
- **Hornet alerts are not trustworthy alone.** On real photos, 46 % of other insects (mostly wasps) and 43 % of bees were called "hornet". Treat a hornet alert as "check the camera", not as a confirmed sighting.
- **Varroa is synthetic-only.** No labeled real bee crops were available; the public VarroaDataset is the next check. The synthetic prevalence (about 45 %) is much higher than real infestations, so expect lower precision in the field.
- **Small hive beetles** are found in only 45 % of cases even on synthetic data.
- Latency is an estimate, not a measurement on a Pi.

## License

AGPL-3.0, because the models are derived from Ultralytics YOLO11 (AGPL-3.0); see [ADR-0008](../../docs/adr/0008-detector-licensing.md). The CC BY photos behind the cutouts require attribution: [`ATTRIBUTION.tsv`](ATTRIBUTION.tsv) lists every photo with its license, source URL and iNaturalist observer id.
