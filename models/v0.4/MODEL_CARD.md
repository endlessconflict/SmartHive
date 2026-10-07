# SmartHive vision models v0.4

Two ncnn models for the entrance camera on the hive node: a detector (stage 1) and a Varroa crop classifier (stage 2). Released 2026-10-07. Full evaluation: [vision results](../../docs/03-vision/07-results.md).

What changed from [v0.2](../v0.2/MODEL_CARD.md): the detector also trains on 2,333 real iNaturalist photos labeled automatically ([ADR-0010](../../docs/adr/0010-real-photos-with-automatic-labels.md)). Stage 2 is the v0.2 classifier, unchanged (same files, same checksums).

## Files

| Path | What | Input | Output |
|---|---|---|---|
| `stage1/model.ncnn.{param,bin}` | YOLO11n detector, 2.59 M params, 1.6 GFLOPs | `in0`, 1×3×320×320, RGB, 0 to 1, letterboxed | `out0`, 8×2100 (4 box + 4 class scores) |
| `stage2/model.ncnn.{param,bin}` | YOLO11n-cls classifier, 2.81 M params, 0.13 GFLOPs | `in0`, 1×3×128×128, RGB, 0 to 1 | `out0`, 2 class probabilities |
| `*/metadata.yaml` | Class names and export settings from Ultralytics | | |
| `ATTRIBUTION.tsv` | Every real photo used in training: as a cutout in the synthetic scenes or as a whole photo, with license, source URL and iNaturalist observer id | | |
| `SHA256SUMS` | Checksums; check with `sha256sum -c SHA256SUMS` from this folder | | |

Classes: stage 1 `0 bee, 1 hornet, 2 shb, 3 other_insect`; stage 2 `0 clean, 1 varroa`.

Run them with [`vision/pipeline.py`](../../vision/pipeline.py), which needs only `numpy`, `opencv-python-headless` and `ncnn` ([`edge/requirements.txt`](../../edge/requirements.txt)):

```python
import cv2
from pathlib import Path
from vision.pipeline import Detector

det = Detector(Path("models/v0.4/stage1"), Path("models/v0.4/stage2"))
record = det(cv2.imread("frame.jpg"))  # full-resolution BGR frame
```

Operating thresholds: bee 0.35, hornet 0.45, shb 0.5, other_insect 0.5, varroa 0.6. Alerts use k-of-n aggregation (hornet 3 of 10 frames, beetle 2 of 10).

## Training data

Stage 1 trains on two sources together:

- **Synthetic entrance scenes (tier S)**: the 3,400 training scenes of `S-images-entrance-v0.2-s2`, the same as v0.2. Insects are half procedurally drawn, half real-photo cutouts (626 photos); mites are drawn at physical scale; boards are procedural.
- **Real photos with automatic labels**: 2,333 iNaturalist photos (675 bee, 882 hornet, 776 other insect; 1,081 CC0 and 1,252 CC BY) with 2,410 boxes. The species comes from the iNaturalist identification; the boxes come from YOLOE text prompts ([`vision/pseudolabel.py`](../../vision/pseudolabel.py)). A visual check of 15 random photos found 2 wrong boxes, 1 partial box and 2 photos with insects left unboxed.

No training photo, and no other photo of the same observation, is in the frozen tier P evaluation split. Photographers do overlap with tier P (see limitations).

Stage 2 is the v0.2 classifier: 17,520 clean and 14,566 varroa crops cut from the v0.2 synthetic frames.

Starting weights: Ultralytics `yolo11n.pt` (COCO) and `yolo11n-cls.pt` (ImageNet). Stage 1: 30 epochs at 320 px, the same recipe as v0.2; stage 2: 12 epochs at 128 px. CPU only.

## Results

| Tier | Test | v0.4 | v0.2 |
|---|---|---|---|
| S | Detector val (v0.2 val set, 600 scenes): mAP50 / mAP50-95 | 0.775 / 0.440 | 0.781 / 0.437 |
| S | Full ncnn pipeline, 200 fresh scenes: hornet P / R | 1.00 / 0.92 | 1.00 / 0.91 |
| S | Same: bee P / R | 0.94 / 0.93 | 0.95 / 0.92 |
| S | Same: beetle P / R | 0.89 / 0.54 | 0.79 / 0.45 |
| S | Same: Varroa on bees P / R | 0.96 / 0.93 | 0.96 / 0.92 |
| P | iNaturalist test split, 600 photos, image-level accuracy (chance 0.333) | **0.728** | 0.433 |
| P | Same: hornet R / P | **0.83 / 0.68** | 0.69 / 0.43 |
| P | Same: bee R / P | 0.75 / 0.77 | 0.57 / 0.42 |
| P | Same: other insect R / P | 0.61 / 0.79 | 0.05 / 0.69 |
| Edge | Raspberry Pi 3B, estimated | same as v0.2: stage 1 ≈ 241 ms, stage 2 ≈ 34 ms per crop, peak memory 145 MB | |

The architecture and input size are unchanged, so latency and memory are those measured for v0.2.

## Intended use

Research prototype for the SmartHive node: count bees, flag possible hornets and beetles, estimate the share of bees carrying a visible Varroa mite, at a top-down entrance camera.

## Limitations

- **Not validated on our camera.** No tier C or F data exists yet. The real-photo test uses iNaturalist side views on flowers and hands, not our entrance seen from above.
- **Hornet alerts still need confirmation.** On real photos, 22 % of other insects (mostly wasps) and 16 % of bees were called "hornet", down from 46 % and 43 % in v0.2. Hornet precision (0.68) is just under the 0.70 target and recall (0.83) under 0.90.
- **Photographer overlap.** A few prolific observers took most iNaturalist hornet photos, so the training photos and the tier P test share photographers (not photos or observations). The tier P numbers may be somewhat optimistic. An observer-disjoint test would leave 8 hornets, too few to measure.
- **Varroa is synthetic-only.** No labeled real bee crops were available; the public VarroaDataset is the next check. The synthetic prevalence (about 45 %) is much higher than real infestations, so expect lower precision in the field.
- **Small hive beetles** are found in 54 % of cases on synthetic data and cannot be tested on real images (2 photos).
- Latency is an estimate, not a measurement on a Pi.

## License

AGPL-3.0, because the models are derived from Ultralytics YOLO11 (AGPL-3.0); see [ADR-0008](../../docs/adr/0008-detector-licensing.md). The CC BY photos require attribution: [`ATTRIBUTION.tsv`](ATTRIBUTION.tsv) lists every one.
