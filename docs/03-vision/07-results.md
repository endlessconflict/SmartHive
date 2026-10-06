# Results

Status: Three iterations done; **v0.2 is the release model** ([`models/v0.2`](../../models/v0.2/MODEL_CARD.md)). Date of the runs: 2026-10-06.

Every number names its tier: **S** synthetic (our generators), **P** public real photos (iNaturalist, frozen split), **C/F** our own camera (none yet). Only tier P says anything about real insects, and even tier P is not the entrance camera.

## Summary

- Synthetic data works for training the pipeline end to end. On fresh synthetic scenes (tier S), the full node pipeline finds 96 % of hornet scenes with no false hornets, and classifies Varroa on detected bees with 0.96 precision and 0.92 recall. Its Varroa rate estimate is 39.4 % against a true 41.4 %.
- Transfer to real insects is partial. Trained on drawn insects only (v0.1), the detector was at chance on real photos (35.8 % against 33.3 %). Adding real-photo cutouts (v0.2) raised that to 43.3 % and real bee recall from 0.17 to 0.57, on a frozen test split that no training or tuning ever touched.
- The open problem is hornet over-confidence: real wasps, flies and bees are still called "hornet" too often (hornet precision 0.43 on real photos). Adding more distractors in v0.3 did not fix it, so v0.3 was not released.
- The models fit the hardware. On a Raspberry Pi 3B the estimate is about 0.24 s for stage 1 and 34 ms per bee crop for stage 2, so a frame with 15 bees takes about 0.75 s (1.4 s at the pessimistic end of the range). The pipeline peaks at 145 MB of RAM. These are estimates anchored to ncnn's published Pi measurements, not measurements on our Pi.
- Not measurable yet: Varroa on real bees, small hive beetles on real images, and anything on our own camera. Each has a Jira item.

## Setup

| | Stage 1 detector | Stage 2 Varroa classifier |
|---|---|---|
| Model | YOLO11n, COCO-pretrained, 2.59 M params, 1.6 GFLOPs at 320 px | YOLO11n-cls, ImageNet-pretrained, 2.81 M params, 0.13 GFLOPs at 128 px |
| Input | 640×480 frame letterboxed to 320 | 128×128 crop of a bee from the 1640×1232 frame |
| Classes | bee, hornet, shb, other_insect | clean, varroa |
| Training | CPU (4 cores, no GPU), batch 32, mosaic, 180° rotation, flips, HSV | CPU, batch 128, RandAugment, rotation, flips |
| Runtime on the node | ncnn, fp16 storage, 3 threads, no torch ([`vision/pipeline.py`](../../vision/pipeline.py)) | same |

A 30-epoch stage 1 run takes 1.5 to 2 hours on the 4-core CPU; stage 2, about 50 minutes for 12 epochs.

## Iterations

| | v0.1 | v0.2 (released) | v0.3 |
|---|---|---|---|
| Idea | Procedural insects only ([ADR-0009](../adr/0009-procedural-insect-rendering.md)) | Half of the insects from real-photo cutouts; mites painted on real bees; 15 % random-texture backgrounds | v0.2 plus a second cutout pool and more distractors per scene (other insects in 65 % of scenes, up to 6) |
| Dataset | `S-images-entrance-v0.1-s1` | `S-images-entrance-v0.2-s2` | `S-images-entrance-v0.3-s3` |
| Real cutouts | 0 | 626 (234 bee, 245 hornet, 147 other) | 1,383 (505 bee, 539 hornet, 339 other) |
| Training | 27 of 30 epochs (stopped by the 2-hour job limit), from COCO | 30 epochs, from COCO | 15 epochs fine-tuned from v0.2 |
| Tier S, own val set: mAP50 / mAP50-95 | 0.865 / 0.549 | 0.781 / 0.437 | 0.770 / 0.432 |
| Tier P calib: accuracy | 0.320 | 0.425 | 0.428 |
| Decision | Baseline | Released | Not released: hornet false positives got worse |

Tier S numbers are not comparable across columns, because each version has its own validation set, and v0.2/v0.3 validation includes real cutouts, which are harder. Tier P is the comparable row.

All cutout pools were checked for overlap with the tier P split: zero photos in common.

### v0.2 per class, tier S (v0.2 val, 600 scenes)

| Class | mAP50 | mAP50-95 |
|---|---|---|
| bee | 0.948 | 0.600 |
| hornet | 0.921 | 0.561 |
| shb | 0.684 | 0.282 |
| other_insect | 0.570 | 0.306 |
| all (precision 0.834, recall 0.710) | 0.781 | 0.437 |

Stage 2 (v0.2 val crops, 5,577 crops, 46 % with a visible mite): top-1 accuracy 0.877.

## Tier P: real photos

Protocol: [training and evaluation](05-training-and-evaluation.md#how-the-tier-p-test-works). An image-level test on iNaturalist photos: the most confident detection over three scales names the photo. 600 photos per split, 200 per class, chance 33.3 %. Model selection used only the calibration split. The test split was opened once, after the choice.

| Test split (600 photos) | v0.1 | **v0.2** | v0.3 |
|---|---|---|---|
| Accuracy | 0.358 | **0.433** | 0.422 |
| Bee recall / precision | 0.170 / 0.301 | **0.565 / 0.419** | 0.350 / 0.435 |
| Hornet recall / precision | 0.745 / 0.365 | **0.690 / 0.433** | 0.800 / 0.392 |
| Other-insect recall | 0.160 | 0.045 | 0.115 |
| Real other insects called "hornet" | 123 of 200 | **92 of 200** | 121 of 200 |
| Real bees called "hornet" | 130 of 200 | **85 of 200** | 123 of 200 |

v0.2 confusion on the test split (rows: true class, columns: prediction):

| | bee | hornet | other | shb | none |
|---|---|---|---|---|---|
| bee | 113 | 85 | 2 | 0 | 0 |
| hornet | 57 | 138 | 2 | 2 | 1 |
| other_insect | 98 | 92 | 9 | 1 | 0 |

How to read this:

- Real-photo cutouts are what moved the needle (v0.1 to v0.2). The drawn insects teach shapes and scale; real appearance had to come from photos.
- The detector still finds *something* in practically every photo (any-detection rate above 99 %). Localization transfers better than classification.
- "Other insect" is the weak class on real photos. In iNaturalist it includes wasps (*Polistes*, *Vespula*), bumblebees and flies. Wasps really do look like small hornets. On a real entrance the other-insect traffic is mostly flies and ants, and the hornet threshold plus the k-of-n rule add protection. But a 0.43 hornet precision on single photos means hornet alerts are not ready to be trusted without the field test.
- These photos are side views on flowers, leaves and hands. Our camera looks down at a board. Real performance at the entrance can be better (bees from above on a plain board) or worse (crowding, blur). Only our own captures can settle it.

## Tier S: the whole node pipeline

[`vision/eval_system.py`](../../vision/eval_system.py) on 200 fresh full-resolution scenes from the validation sprite library (procedural insects only, no cutouts), with the ncnn models, the real crop geometry and the operating thresholds (bee 0.35, hornet 0.45, shb 0.5, other 0.5, varroa 0.6). Release v0.2:

| Measure | Value |
|---|---|
| Bee precision / recall (IoU 0.5) | 0.945 / 0.916 |
| Hornet precision / recall | 1.000 / 0.909 |
| Scenes with a hornet in which at least one is detected | 0.959 |
| SHB precision / recall | 0.787 / 0.453 |
| Scenes with a beetle in which at least one is detected | 0.660 |
| Other-insect precision / recall | 0.974 / 0.426 |
| Varroa on matched walking bees: precision / recall | 0.963 / 0.917 (617 TP, 24 FP, 56 FN, 930 TN) |
| Varroa rate: true / estimated | 41.4 % / 39.4 % |

Small hive beetles are 5 to 7 mm, about 10 px at the 320 px detector input, and recall shows it. The fix is known: a 416 px input (about 1.7 times the cost) or a beetle-specific crop pass, to try after the camera is fixed.

The synthetic Varroa prevalence (about 45 % of bees) is far above real infestations. Precision at a realistic 2 to 5 % prevalence will be lower, because false positives then outnumber true ones. Before the field test, the Varroa threshold should be re-tuned on crops sampled at realistic prevalence.

## Latency on the Raspberry Pi 3B (estimate)

[`vision/bench.py`](../../vision/bench.py) ran nine of ncnn's reference networks here and compared them with ncnn's published timings for a Raspberry Pi 3 Model B+ (Cortex-A53, 1.4 GHz). The median ratio was applied to our models, scaled to the 3B's 1.2 GHz. The range uses the smallest and largest ratio among the reference networks.

| Model | Host (x86), 4 threads | Pi 3B estimate, 4 threads | Pi 3B estimate, 1 thread |
|---|---|---|---|
| Stage 1, YOLO11n 320 | 10.9 ms | **241 ms** (162 to 455) | 330 ms (223 to 377) |
| Stage 2, YOLO11n-cls 128, per crop | 1.5 ms | **34 ms** (23 to 64) | 33 ms (22 to 38) |
| Frame with 15 sharp bees | | **≈ 0.75 s** (0.5 to 1.4) | ≈ 0.8 s |

As a cross-check, nanodet_m (0.72 GFLOPs) measures 115 ms on the Pi 3B+ with 4 threads. Our stage 1 costs 2.2 times the FLOPs, which gives about 250 ms at 1.4 GHz, so the estimate is plausible.

Peak resident memory of the two-stage pipeline with both models loaded and a full frame processed: **145 MB** (measured on the build machine; ncnn's memory use is similar across architectures). The budget is 250 MB.

A finding to keep: with all cores busy with other work, ncnn with 4 threads was over 100 times slower than with 1 thread. The pipeline defaults to 3 threads, leaving one core for the other node services ([edge deployment](06-edge-deployment.md#threads-leave-a-core-free)).

## Against the acceptance criteria

Targets from [training and evaluation](05-training-and-evaluation.md#acceptance-criteria).

| Criterion | Target | v0.2 | Status |
|---|---|---|---|
| Hornet recall (tier P) | ≥ 0.90 | 0.69 image-level on photos; 0.91 per hornet and 0.96 per scene on tier S | Not met on real photos |
| Hornet precision (tier P) | ≥ 0.70 | 0.43 image-level | Not met |
| Bee detection recall (tier P) | ≥ 0.85 | No boxes in tier P; image-level bee recall 0.57; 0.92 on tier S | Not measurable as defined |
| Varroa crop recall / precision (tier P) | ≥ 0.75 / ≥ 0.70 | No real crops available; 0.92 / 0.96 on tier S | Not measurable yet |
| False threat events per day | ≤ 1 | Needs sequences (generator v0.4) | Not measured |
| Stage 1 latency p95 on the Pi | ≤ 1.0 s | ≈ 0.24 s estimated (up to 0.46 s) | Met, as an estimate |
| Frame with 15 bees on the Pi | ≤ 2.0 s | ≈ 0.75 s estimated (up to 1.4 s) | Met, as an estimate |
| Vision service memory | ≤ 250 MB | 145 MB peak | Met |

## What the numbers do not show

- Entrance-camera performance (tier C/F). Needs the camera (Jira HW-01) and the field test (HW-04).
- Varroa on real bees. The public VarroaDataset (13.5k labeled real bee crops) is the next check, from a machine with Zenodo access (Jira US09).
- Small hive beetles on real images: 2 photos exist in the source snapshot. Tier S only.
- False alerts over time. The aggregation rule is unit-tested; its false-event rate needs synthetic sequences.

## Next iteration (v0.4), in order

1. **Real board backgrounds** from our camera (tier C), the largest single domain change left (Jira EN-12).
2. **Hornet versus wasp**: make the procedural renderer and the cutouts cover local wasps explicitly as `other_insect`, and add hard-negative mining. Collect the calib photos the current model calls "hornet", look at them, then add matching negatives to the generator. Never use test photos for this.
3. **Per-class operating thresholds** chosen on the calibration split (still never the test split), and the Varroa threshold re-tuned at realistic prevalence.
4. **416 px stage 1** trial for small hive beetles, accepting about 1.7 times the stage 1 cost if the Pi budget allows.
5. **Sequences** in the generator, to measure false threat events per day and the motion gate.
6. **Public Varroa data** (VarroaDataset, TU Wien, [Zenodo 4085044](https://zenodo.org/record/4085044)) as tier P for stage 2.

## Reproduce

```bash
python -m vision.inat download --src data/raw/inat --out data/raw/inat_pool --per-class 600 --seed 1 --exclude vision/splits/P-inat-v1.tsv
python -m simulation.images.cutouts data/raw/inat_pool data/assets/cutouts-v1
python -m simulation.images.compose --out data/sim/S-images-entrance-v0.2-s2 --n 4000 --seed 2 --cutouts data/assets/cutouts-v1
python -m vision.train stage1 data/sim/S-images-entrance-v0.2-s2 --epochs 30 --name s1-v0.2-yolo11n-320
python -m vision.train stage2 data/sim/S-images-entrance-v0.2-s2 --epochs 12 --name s2-v0.2-yolo11n-cls-128
python -m vision.eval_real runs/detect/runs/stage1/s1-v0.2-yolo11n-320/weights/best.pt --split calib
python -m vision.export runs/detect/runs/stage1/s1-v0.2-yolo11n-320/weights/best.pt --imgsz 320
python -m vision.export runs/classify/runs/stage2/s2-v0.2-yolo11n-cls-128/weights/best.pt --imgsz 128
python -m vision.eval_system <stage1_ncnn_dir> <stage2_ncnn_dir> --n 200
python -m vision.bench <stage1_ncnn_dir>:320 <stage2_ncnn_dir>:128
```

Note: generator v0.3 changed the distractor rates, so regenerating v0.2 exactly needs the generator at commit `617ee39`.
