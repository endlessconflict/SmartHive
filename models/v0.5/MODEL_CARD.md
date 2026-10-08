# SmartHive vision models v0.5

Three ncnn models for the entrance camera on the hive node: a detector (stage 1), a species verifier for hornet and other-insect candidates (stage 1b) and a Varroa crop classifier (stage 2). Released 2026-10-08. Full evaluation: [vision results](../../docs/03-vision/07-results.md).

What changed from [v0.4](../v0.4/MODEL_CARD.md):

- Every training label was made with OSI-licensed tools ([ADR-0011](../../docs/adr/0011-osi-clean-automatic-labeling.md)).
- About five times more real photos: the 2026 iNaturalist snapshot, weighted toward the insects that look like hornets and bees, plus Open Images photos with human-drawn boxes.
- A new stage 1b: a species verifier.
- YOLO26n and YOLO26n-cls instead of YOLO11n.

## Files

| Path | What | Input | Output |
|---|---|---|---|
| `stage1/model.ncnn.{param,bin}` | YOLO26n detector, 2.4 M params | `in0`, 1×3×320×320, RGB, 0 to 1, letterboxed | `out0`, 8×2100 (4 box + 4 class scores) |
| `stage1b/model.ncnn.{param,bin}` | YOLO26n-cls species verifier | `in0`, 1×3×160×160, RGB, 0 to 1 | `out0`: bee, hornet, other_insect |
| `stage2/model.ncnn.{param,bin}` | YOLO26n-cls Varroa classifier | `in0`, 1×3×128×128, RGB, 0 to 1 | `out0`: clean, varroa |
| `*/metadata.yaml` | Class names and export settings from Ultralytics | | |
| `ATTRIBUTION.tsv` | Every real photo used in training (11,392): source, license, author or iNaturalist observer, URL, and whether it was used whole or as a cutout | | |
| `SHA256SUMS` | Checksums; check with `sha256sum -c SHA256SUMS` from this folder | | |

```python
import cv2
from pathlib import Path
from vision.pipeline import Detector

det = Detector(Path("models/v0.5/stage1"), Path("models/v0.5/stage2"), verifier=Path("models/v0.5/stage1b"))
record = det(cv2.cvtColor(cv2.imread("frame.jpg"), cv2.COLOR_BGR2RGB))  # full-resolution RGB frame
```

Operating points (defaults in [`vision/pipeline.py`](../../vision/pipeline.py)):

- Detector thresholds: bee 0.25, hornet 0.30, shb 0.35, other_insect 0.5. These were chosen on synthetic scenes (seed 8) kept apart from the synthetic test.
- Verifier rule `decide()`:
  - a hornet stays a hornet only if the verifier gives it at least 0.2;
  - a bee or other insect changes class only if the verifier is at least 0.6 sure.
  These two values were chosen on tier P v2 calibration photos: the most accurate pair with hornet recall ≥ 0.90 and precision ≥ 0.70.
- Varroa threshold: 0.6.
- Alerts use k-of-n aggregation: hornet 3 of 10 frames, beetle 2 of 10.

## Training data

| Model | Data |
|---|---|
| Stage 1 | **Synthetic scenes:** 6,800 entrance scenes (seeds 5 and 6) with procedural insects and 6,497 real-photo cutouts (SAM 2.1 masks). **Real photos:** 10,783 iNaturalist photos with automatic boxes; 3,000 mosaics of those photos at entrance scale; 609 Open Images photos with human boxes, kept only when the verifier calls every bee a honeybee. Trained 20 epochs from COCO, then fine-tuned 6 epochs with the second synthetic set |
| Stage 1b | 12,732 real crops from the auto-labeled photos (bee, hornet, look-alikes in 23 groups) and 7,988 synthetic top-down crops; photographers in hash bucket 9 held out for validation |
| Stage 2 | 32,613 crops from the seed-5 synthetic scenes (17,778 clean, 14,835 with a visible mite). Mites are drawn at physical scale on procedural bees and on real-photo bee cutouts |

Real photos: iNaturalist research-grade observations (CC0 or CC BY) from the 2026-09-27 snapshot. No training photo shares a photo, an observation or a photographer with the tier P v2 test, and none shares a photo or an observation with tier P v1. Open Images V7 images are CC BY 2.0, its boxes CC BY 4.0.

Automatic boxes: prompt-free YOLOE-26l proposals kept by our insectness classifier. Against held-out Open Images human boxes, precision is 0.65 and recall 0.65 at IoU 0.5. Audits of random samples are in the [results](../../docs/03-vision/07-results.md).

## Results

| Tier | Test | v0.5 | v0.4 |
|---|---|---|---|
| P v2 | Real photos, 1,612, no photographer shared with training: accuracy (chance 0.333) | **0.886** | 0.652 |
| P v2 | Hornet recall / precision | **0.893 / 0.899** | 0.748 / 0.570 |
| P v2 | Look-alike insects called "hornet" | **34 of 635** | 210 of 635 |
| P v2 | Bee recall / precision | **0.852 / 0.928** | 0.778 / 0.726 |
| P v1 | Real photos, 600 (older test): accuracy | **0.862** | 0.728 |
| S | Full ncnn pipeline, 200 fresh scenes: bee precision / recall | **0.956 / 0.932** | 0.935 / 0.932 |
| S | Hornet precision / recall | 0.973 / **0.935** | 1.000 / 0.922 |
| S | Scenes with a beetle in which one is found | **0.83** | 0.74 |
| S | Varroa on bees: precision / recall | **0.987** / 0.900 | 0.964 / 0.927 |
| S | Varroa false positives on clean bees | **0.8 %** | 2.5 % |
| Edge | Raspberry Pi 3B, estimated: stage 1 / stage 2 per bee / verifier per candidate | 251 / 33 / 46 ms | 241 / 34 / – ms |
| Edge | Peak memory, all models loaded | 173 MB | 145 MB |

## Intended use

Research prototype for the SmartHive node: count bees, flag possible hornets and beetles, and estimate the share of bees carrying a visible Varroa mite, from a top-down entrance camera.

## Limitations

- **Not validated on our camera.** No tier C or F data exists yet. The real-photo tests use iNaturalist side views, not our entrance seen from above.
- **Hornets:**
  - Single-photo hornet recall is 0.893, just under the 0.90 target; precision (0.899) is well above its 0.70 target.
  - The k-of-n rule works on several frames, so event-level recall should be higher, but that is not measured yet.
  - The look-alikes still called hornet most often are *Milesia* and *Siricidae* (3 of 20 each), *Scoliidae* (4 of 40) and *Vespula* (5 of 70; v0.4: 45).
- **Varroa is synthetic-only:**
  - The 2026 snapshot holds only 37 openly licensed Varroa photos. The VarroaDataset is not reachable from the build machine.
  - Recall on synthetic bees is lower than v0.4's (0.900 vs 0.927).
  - The false-positive rate is three times lower, which is what decides precision at real infestation levels (2 to 5 %).
- **Small hive beetles** are found in 66 % of cases on synthetic data and cannot be tested on real images (59 photos in the snapshot).
- **Automatic boxes are not perfect:** about a third disagree with human boxes at IoU 0.5, mostly partial or loose boxes.
- **Latency is an estimate**, not a measurement on a Pi.

## License

AGPL-3.0, because the models derive from Ultralytics YOLO26 (AGPL-3.0); see [ADR-0008](../../docs/adr/0008-detector-licensing.md). All tools used to make the training data have OSI-licensed weights (ADR-0011). CC BY photos require attribution: [`ATTRIBUTION.tsv`](ATTRIBUTION.tsv) lists every one.
