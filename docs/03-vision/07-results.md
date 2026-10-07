# Results

Status: Four iterations done; **v0.4 is the release model** ([`models/v0.4`](../../models/v0.4/MODEL_CARD.md)). Runs dated 2026-10-06 and 2026-10-07.

Every number names its tier: **S** synthetic (our generators), **P** public real photos (iNaturalist, frozen split), **C/F** our own camera (none yet). Only tier P says anything about real insects, and even tier P is not the entrance camera.

## Summary

- Synthetic data works for training the pipeline end to end. On fresh synthetic scenes (tier S), the v0.4 node pipeline finds 92 % of hornets with no false hornets, and classifies Varroa on detected bees with 0.96 precision and 0.93 recall. Its Varroa rate estimate is 39.7 % against a true 41.3 %.
- Transfer to real insects came from real appearance, step by step. Drawn insects only (v0.1): at chance on real photos (35.8 % against 33.3 %). Real-photo cutouts pasted into the scenes (v0.2): 43.3 %. Whole real photos labeled automatically, added to training (v0.4): **72.8 %**, on a frozen test split that no training or tuning touched.
- The hornet problem shrank but is not solved. On real photos, v0.4 calls 22 % of other insects (mostly wasps) and 16 % of bees "hornet", down from 46 % and 43 % with v0.2. Hornet recall is 0.83 and precision 0.68, against targets of 0.90 and 0.70.
- Adding real photos cost nothing on the synthetic entrance scenes: tier S detector and pipeline numbers are equal or better than v0.2.
- The models fit the hardware. On a Raspberry Pi 3B the estimate is about 0.24 s for stage 1 and 34 ms per bee crop for stage 2, so a frame with 15 bees takes about 0.75 s (1.4 s at the pessimistic end). The pipeline peaks at 145 MB of RAM. These are estimates anchored to ncnn's published Pi measurements, not measurements on our Pi.
- Not measurable yet: Varroa on real bees, small hive beetles on real images, and anything on our own camera. Each has a Jira item.

## Setup

| | Stage 1 detector | Stage 2 Varroa classifier |
|---|---|---|
| Model | YOLO11n, COCO-pretrained, 2.59 M params, 1.6 GFLOPs at 320 px | YOLO11n-cls, ImageNet-pretrained, 2.81 M params, 0.13 GFLOPs at 128 px |
| Input | 640×480 frame letterboxed to 320 | 128×128 crop of a bee from the 1640×1232 frame |
| Classes | bee, hornet, shb, other_insect | clean, varroa |
| Training | CPU (4 cores, no GPU), batch 32, mosaic, 180° rotation, flips, HSV | CPU, batch 128, RandAugment, rotation, flips |
| Runtime on the node | ncnn, fp16 storage, 3 threads, no torch ([`vision/pipeline.py`](../../vision/pipeline.py)) | same |

A 30-epoch stage 1 run takes 1.5 hours on 3,400 synthetic scenes and 2 hours with the 2,333 real photos added; stage 2, about 50 minutes for 12 epochs.

## Iterations

| | v0.1 | v0.2 | v0.3 | v0.4 (released) |
|---|---|---|---|---|
| Idea | Procedural insects only ([ADR-0009](../adr/0009-procedural-insect-rendering.md)) | Half of the insects from real-photo cutouts; mites painted on real bees; 15 % random-texture backgrounds | v0.2 plus a second cutout pool and more distractors per scene | v0.2 scenes plus whole real photos with automatic labels ([ADR-0010](../adr/0010-real-photos-with-automatic-labels.md)) |
| Training data | `S-images-entrance-v0.1-s1` | `S-images-entrance-v0.2-s2` | `S-images-entrance-v0.3-s3` | `S-images-entrance-v0.2-s2` + `R-inat-pseudo-v1` (2,333 photos, 2,410 boxes) |
| Real photos used | 0 | 626 as cutouts | 1,383 as cutouts | 626 as cutouts + 2,333 whole |
| Training | 27 of 30 epochs (stopped by the 2-hour job limit), from COCO | 30 epochs, from COCO | 15 epochs fine-tuned from v0.2 | 30 epochs, from COCO (same recipe as v0.2) |
| Tier S, own val set: mAP50 / mAP50-95 | 0.865 / 0.549 | 0.781 / 0.437 | 0.770 / 0.432 | 0.775 / 0.440 (v0.2 val set) |
| Tier P calib: accuracy | 0.320 | 0.425 | 0.428 | **0.737** |
| Decision | Baseline | Released, now superseded | Not released: hornet false positives got worse | Released |

Tier S numbers of v0.1 to v0.3 are not comparable across columns, because each version has its own validation set. v0.4 is validated on the v0.2 set, so those two are comparable. Tier P is the comparable row.

No training photo, cutout or whole, is in the tier P split, and no training photo comes from an observation that has a photo in tier P (checked through the observation id). Photographers do overlap; see [below](#caveat-photographers-overlap).

### Why v0.4 worked where v0.3 did not

v0.3 added more pasted cutouts of wasps and bumblebees; the model still learned "striped insect with a cutout edge on a board" and kept calling real wasps hornets. v0.4 shows the detector whole photos: the insect with its real lighting, focus and surroundings, and many real *Polistes* and *Vespula* wasps labeled `other_insect`. This is the cheap version of what a 3D render followed by a diffusion pass would try to buy. [ADR-0010](../adr/0010-real-photos-with-automatic-labels.md) compares the two.

The labels are automatic: the species comes from iNaturalist, the box from YOLOE text prompts ([`vision/pseudolabel.py`](../../vision/pseudolabel.py)), about 4 photos per second on the CPU. 2,333 of 3,900 photos got a confident box. A visual check of 15 random photos found 2 wrong boxes (a wild comb and a flower labeled "bee"), 1 partial box, and 2 photos with insects left unboxed.

### Detector per class, tier S (v0.2 val, 600 scenes)

| Class | v0.2 mAP50 / mAP50-95 | v0.4 mAP50 / mAP50-95 |
|---|---|---|
| bee | 0.948 / 0.600 | 0.948 / 0.607 |
| hornet | 0.921 / 0.561 | 0.909 / 0.565 |
| shb | 0.684 / 0.282 | 0.681 / 0.285 |
| other_insect | 0.570 / 0.306 | 0.563 / 0.304 |
| all | 0.781 / 0.437 (P 0.834, R 0.710) | 0.775 / 0.440 (P 0.806, R 0.707) |

Stage 2 is the same in v0.2 and v0.4 (v0.2 val crops, 5,577 crops, 46 % with a visible mite): top-1 accuracy 0.877.

## Tier P: real photos

Protocol: [training and evaluation](05-training-and-evaluation.md#how-the-tier-p-test-works). An image-level test on iNaturalist photos: the most confident detection over three scales names the photo. 600 photos per split, 200 per class, chance 33.3 %. Model selection used only the calibration split. The test split was opened once per candidate, after the choice.

| Test split (600 photos) | v0.1 | v0.2 | v0.3 | **v0.4** |
|---|---|---|---|---|
| Accuracy | 0.358 | 0.433 | 0.422 | **0.728** |
| Bee recall / precision | 0.170 / 0.301 | 0.565 / 0.419 | 0.350 / 0.435 | **0.750 / 0.765** |
| Hornet recall / precision | 0.745 / 0.365 | 0.690 / 0.433 | 0.800 / 0.392 | **0.825 / 0.676** |
| Other-insect recall / precision | 0.160 / 0.381 | 0.045 / 0.692 | 0.115 / 0.622 | **0.610 / 0.792** |
| Real other insects called "hornet" | 123 of 200 | 92 of 200 | 121 of 200 | **44 of 200** |
| Real bees called "hornet" | 130 of 200 | 85 of 200 | 123 of 200 | **32 of 200** |
| Photos with no detection | 0 % | 0.2 % | 0 % | 1.8 % |

v0.4 confusion on the test split (rows: true class, columns: prediction):

| | bee | hornet | other | shb | none |
|---|---|---|---|---|---|
| bee | 150 | 32 | 16 | 0 | 2 |
| hornet | 14 | 165 | 16 | 1 | 4 |
| other_insect | 29 | 44 | 122 | 0 | 5 |

How to read this:

- Real appearance is what moves the needle: cutouts first (v0.1 to v0.2), whole photos far more (v0.2 to v0.4). Drawn insects still matter for what photos cannot give: the top-down view, the scale at our camera, the board, and exact mite labels.
- The remaining hornet errors are mostly wasps. On a real entrance in Panama the other-insect traffic is mostly flies, ants and stingless bees, and the hornet threshold plus the k-of-n rule add protection. Still, a 0.68 precision on single photos means a hornet alert should say "check the camera" until the field test.
- These photos are side views on flowers, leaves and hands. Our camera looks down at a board. Real performance at the entrance can be better (insects from above on a plain board) or worse (crowding, blur). Only our own captures can settle it.

### Caveat: photographers overlap

A few prolific observers took most of the iNaturalist hornet photos in the snapshot. Training pools and tier P share no photo and no observation, but they do share photographers: 94 % of the pool's hornet photos and about 70 % of its bee photos come from someone who also has a photo in tier P. Same photographer can mean the same camera, garden and style, which can make tier P look better than truly unseen photos. This applies to v0.2 (its cutouts come from the same pools) and to v0.4 alike, so the comparison between them is fair, but the absolute numbers may be somewhat optimistic. An observer-disjoint test would leave 8 hornets, too few to measure. A newer iNaturalist snapshot with more photographers would fix this (Jira EN-12).

## Tier S: the whole node pipeline

[`vision/eval_system.py`](../../vision/eval_system.py) on 200 fresh full-resolution scenes from the validation sprite library (procedural insects only, no cutouts), with the ncnn models, the real crop geometry and the operating thresholds (bee 0.35, hornet 0.45, shb 0.5, other 0.5, varroa 0.6). Both releases use the same stage 2.

| Measure | v0.2 | v0.4 |
|---|---|---|
| Bee precision / recall (IoU 0.5) | 0.945 / 0.920 | 0.935 / 0.932 |
| Hornet precision / recall | 1.000 / 0.909 | 1.000 / 0.922 |
| Scenes with a hornet in which at least one is detected | 0.959 | 0.939 |
| SHB precision / recall | 0.787 / 0.453 | 0.891 / 0.538 |
| Scenes with a beetle in which at least one is detected | 0.660 | 0.736 |
| Other-insect precision / recall | 0.974 / 0.429 | 0.995 / 0.451 |
| Varroa on matched walking bees: precision / recall | 0.960 / 0.919 (622 TP, 26 FP, 55 FN, 933 TN) | 0.964 / 0.927 (634 TP, 24 FP, 50 FN, 948 TN) |
| Varroa rate: true / estimated | 41.4 % / 39.6 % | 41.3 % / 39.7 % |

A bug found on the way: the node pipeline handed ncnn a temporary numpy array that Python could free before ncnn read it, so some runs returned noise. The v0.2 numbers above were re-measured after the fix and differ from the first v0.2 report by at most 0.004. The pipeline self-check in CI now runs the detector 20 times on one input and requires the same output.

Small hive beetles are 5 to 7 mm, about 10 px at the 320 px detector input, and recall shows it. The fix is known: a 416 px input (about 1.7 times the cost) or a beetle-specific crop pass, to try after the camera is fixed.

The synthetic Varroa prevalence (about 45 % of bees) is far above real infestations. Precision at a realistic 2 to 5 % prevalence will be lower, because false positives then outnumber true ones. Before the field test, the Varroa threshold should be re-tuned on crops sampled at realistic prevalence.

## Latency on the Raspberry Pi 3B (estimate)

[`vision/bench.py`](../../vision/bench.py) ran nine of ncnn's reference networks here and compared them with ncnn's published timings for a Raspberry Pi 3 Model B+ (Cortex-A53, 1.4 GHz). The median ratio was applied to our models, scaled to the 3B's 1.2 GHz. The range uses the smallest and largest ratio among the reference networks. v0.4 has the same architecture and input size as v0.2 (the param files are identical; only the weights differ), so the numbers hold for both.

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

| Criterion | Target | v0.4 | Status |
|---|---|---|---|
| Hornet recall (tier P) | ≥ 0.90 | 0.825 image-level on photos; 0.92 per hornet and 0.94 per scene on tier S | Not met on real photos (v0.2: 0.69) |
| Hornet precision (tier P) | ≥ 0.70 | 0.676 image-level | Not met, close (v0.2: 0.43) |
| Bee detection recall (tier P) | ≥ 0.85 | No boxes in tier P; image-level bee recall 0.75; 0.93 on tier S | Not measurable as defined |
| Varroa crop recall / precision (tier P) | ≥ 0.75 / ≥ 0.70 | No real crops available; 0.93 / 0.96 on tier S | Not measurable yet |
| False threat events per day | ≤ 1 | Needs sequences in the generator | Not measured |
| Stage 1 latency p95 on the Pi | ≤ 1.0 s | ≈ 0.24 s estimated (up to 0.46 s) | Met, as an estimate |
| Frame with 15 bees on the Pi | ≤ 2.0 s | ≈ 0.75 s estimated (up to 1.4 s) | Met, as an estimate |
| Vision service memory | ≤ 250 MB | 145 MB peak | Met |

## What the numbers do not show

- Entrance-camera performance (tier C/F). Needs the camera (Jira HW-01) and the field test (HW-04).
- Varroa on real bees. The public VarroaDataset (13.5k labeled real bee crops) is the next check, from a machine with Zenodo access (Jira US09).
- Small hive beetles on real images: 2 photos exist in the source snapshot. Tier S only.
- False alerts over time. The aggregation rule is unit-tested; its false-event rate needs synthetic sequences.

## Next iteration (v0.5), in order

1. **Real board backgrounds** from our camera (tier C), the largest domain change left (Jira EN-12).
2. **More and fresher real photos**: a newer iNaturalist snapshot, which has many more photographers (fixes the overlap caveat) and more photos of local wasps, stingless bees and flies as `other_insect`.
3. **Hard negatives**: look at the calibration photos v0.4 still calls "hornet" and add more of those insect groups. Never use test photos for this.
4. **Per-class operating thresholds** chosen on the calibration split, and the Varroa threshold re-tuned at realistic prevalence.
5. **416 px stage 1** trial for small hive beetles, accepting about 1.7 times the stage 1 cost if the Pi budget allows.
6. **Sequences** in the generator, to measure false threat events per day and the motion gate.
7. **Public Varroa data** (VarroaDataset, TU Wien, [Zenodo 4085044](https://zenodo.org/record/4085044)) as tier P for stage 2.

## Reproduce

```bash
# pools disjoint from tier P
python -m vision.inat download --src data/raw/inat --out data/raw/inat_pool --per-class 600 --seed 1 --exclude vision/splits/P-inat-v1.tsv
python -m vision.inat download --src data/raw/inat --out data/raw/inat_pool2 --per-class 700 --seed 2 --only bee hornet other_insect --exclude vision/splits/P-inat-v1.tsv data/raw/inat_pool/manifest.tsv
# v0.2 synthetic scenes (generator at commit 617ee39) and stage 2
python -m simulation.images.cutouts data/raw/inat_pool data/assets/cutouts-v1
python -m simulation.images.compose --out data/sim/S-images-entrance-v0.2-s2 --n 4000 --seed 2 --cutouts data/assets/cutouts-v1
python -m vision.train stage2 data/sim/S-images-entrance-v0.2-s2 --epochs 12 --name s2-v0.2-yolo11n-cls-128
# v0.4 stage 1: real photos with automatic labels, mixed with the v0.2 scenes
python -m vision.pseudolabel data/raw/inat_pool data/raw/inat_pool2 --out data/sim/R-inat-pseudo-v1
#   data/sim/M-v0.4-s2-plus-inat/stage1/data.yaml lists both train folders; val is the v0.2 val set
python -m vision.train stage1 data/sim/M-v0.4-s2-plus-inat --epochs 30 --name s1-v0.4-yolo11n-320
python -m vision.eval_real runs/detect/runs/stage1/s1-v0.4-yolo11n-320/weights/best.pt --split calib
python -m vision.export runs/detect/runs/stage1/s1-v0.4-yolo11n-320/weights/best.pt --imgsz 320
python -m vision.export runs/classify/runs/stage2/s2-v0.2-yolo11n-cls-128/weights/best.pt --imgsz 128
python -m vision.eval_system <stage1_ncnn_dir> <stage2_ncnn_dir> --n 200
python -m vision.bench <stage1_ncnn_dir>:320 <stage2_ncnn_dir>:128
```
