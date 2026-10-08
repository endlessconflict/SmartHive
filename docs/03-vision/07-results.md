# Results

Status: Five iterations done; **v0.5 is the release** ([`models/v0.5`](../../models/v0.5/MODEL_CARD.md)). Runs dated 2026-10-06 to 2026-10-08.

Every number names its tier: **S** synthetic (our generators), **P** public real photos (iNaturalist, frozen splits), **C/F** our own camera (none yet). Only tier P says anything about real insects, and even tier P is not the entrance camera.

## Summary

- **Real photos, hardest test:** tier P v2 test (1,612 photos; no photographer is shared with training).
  - Accuracy went from 0.652 (v0.4) to **0.886**.
  - Hornet precision from 0.570 to **0.899**, hornet recall from 0.748 to **0.893**.
  - Look-alike insects called "hornet" fell from 210 to **34** of 635, among them *Vespula* (45 to 5), *Polistes* (24 to 4) and *Dolichovespula* (23 to 2).
- **Real photos, older test:** on tier P v1, accuracy went from 0.728 to **0.862**.
- **What made the difference:**
  - five times more real training photos, chosen around the insects that get confused (2026 iNaturalist snapshot, Open Images);
  - a species verifier that takes a second look at every hornet and other-insect candidate;
  - YOLO26n as the detector.
- **Synthetic entrance scenes (tier S):** v0.5 is equal or better than v0.4 on every class except two.
  - Better: bee precision 0.956 (recall unchanged at 0.932); hornet recall 0.935; beetle scenes found 0.83 (from 0.74); other-insect recall 0.60 (from 0.45); Varroa precision 0.987.
  - Hornet precision dropped from 1.000 to 0.973.
  - Varroa recall dropped from 0.927 to 0.900, in exchange for three times fewer false positives on clean bees (0.8 % against 2.5 %), which is what decides precision at real infestation levels.
- **Labeling is FOSS end to end.** We found that the YOLOE text prompts used up to v0.4 load Apple's research-only MobileCLIP weights ([ADR-0011](../adr/0011-osi-clean-automatic-labeling.md)). v0.5 labels come from prompt-free YOLOE proposals and our own insectness classifier. They were scored against human boxes: precision 0.65 and recall 0.65 at IoU 0.5.
- **It still fits the Pi 3B (estimates):** 251 ms for the detector, 33 ms per bee for stage 2, and 46 ms per hornet or other-insect candidate for the verifier. A frame with 15 bees takes about 0.75 s; peak memory is 173 MB.
- **Still open:**
  - hornet recall on single photos (0.893 against 0.90);
  - Varroa and small hive beetles on real images;
  - anything on our own camera.

## Iteration v0.5

### What changed

| | v0.4 | v0.5 |
|---|---|---|
| Real photos for training | 2,333 (2021 snapshot) | 10,783 iNaturalist (2026 snapshot) + 609 Open Images + 3,000 mosaics of them at entrance scale |
| Look-alikes in training | Generic "other insects" (5 taxa) | 23 named groups: *Vespula*, *Dolichovespula*, *Polistes*, *Scoliidae*, *Siricidae*, hornet moth, *Milesia*, *Volucella*, *Eristalis*, *Bombus*, stingless bees, robber flies, sap beetles, wax moth, ... |
| Boxes | YOLOE text prompts (research-only text encoder) | Prompt-free YOLOE-26l + insectness classifier, scored against human boxes |
| Cutouts in the synthetic scenes | 626 | 6,497 |
| Detector | YOLO11n, 320 px | YOLO26n, 320 px, then 6 epochs of fine-tuning with a second, more procedural synthetic set |
| Stage 1b | None | Species verifier (YOLO26n-cls, 160 px crops) on hornet and other-insect candidates |
| Stage 2 | YOLO11n-cls (v0.2) | YOLO26n-cls trained on the v0.5 scenes |
| Real-photo test | Tier P v1 (photographers shared with training) | Tier P v2 (photographers split by hash; 23 look-alike groups) |

### Data

- **iNaturalist, 2026-09-27 snapshot.** The 36 GB metadata archive was streamed once and filtered without being stored ([`vision/inat.py`](../../vision/inat.py)): 743,462 research-grade first photos (CC0 or CC BY) in 27 taxon groups. Tier P v2 and the training pool were drawn from it by photographer bucket (see [training and evaluation](05-training-and-evaluation.md#tier-p-v2-what-changed)): 1,612 test, 981 calibration and 13,090 training photos. Photographers of the earlier pools are kept out of the test, so v0.4 is scored fairly too.
- **Open Images V7.** 2,896 photos whose bees are boxed one by one by people (5,267 boxes). Two uses: ground truth for the labeler, and, after the species check, 609 honeybee photos for training. Open Images' "Bee" means any bee: the verifier rejected 2,022 of 2,631 training photos, and a look at a random sample of them showed bumblebees, hoverflies, *Vespula* wasps, mining and carpenter bees, and a longhorn beetle.
- **Cutouts v3.** 6,497 insects (2,006 bee, 1,496 hornet, 2,995 other) masked with SAM 2.1 from the training pool; a visual check of 24 found 2 bad (a leaf and a hornet abdomen).
- **Mosaics.** 3,000 images of 3×3 auto-labeled photos, which turn an insect that filled a photo into 20 to 100 px, the size the 320 px detector sees at the entrance (31,896 boxes).

Not found: openly licensed real Varroa data. The 2026 snapshot holds 37 CC0/CC BY Varroa photos from a handful of photographers, and the VarroaDataset, BEEHIVE and BeeAlarmed sets are on hosts the build machine cannot reach (Zenodo, Mendeley, a project server).

### Labels: how good are they

Scored with [`vision/labeler.py`](../../vision/labeler.py) `bench` against 302 human bee boxes on 265 held-out Open Images photos, at IoU 0.5:

| Labeler | Precision | Recall |
|---|---|---|
| Prompt-free YOLOE-26l, insect words of its vocabulary only | 0.49 to 0.61 | 0.17 to 0.25 (it finds the bees but names them "squid", "wood duck", "pitcher plant") |
| Prompt-free proposals, any name | | 0.88 of bees have a proposal at IoU 0.5 |
| + insectness classifier v1, p ≥ 0.7 | 0.46 | 0.61 |
| + insectness classifier v2 (partial boxes as negatives), p ≥ 0.7 (**used**) | **0.65** | **0.65** |

Most remaining "errors" are boxes around part of a bee (body without legs or wings) or looser than the human box. A random sample of 20 labeled pool photos showed tiny spurious boxes (a fingertip, a rock) and near-duplicates. A size and overlap rule removed them: no box under a tenth of the largest in the photo, none overlapping a kept box at IoU 0.3. The pool went from 13,090 photos to 10,783 labeled, with 12,732 boxes.

### Species verifier (stage 1b)

Trained on 12,732 real crops from the labeled pool and 7,988 synthetic top-down crops; top-1 0.922 on held-out photographers. Behind the **unchanged v0.4 detector**, on tier P v2 calibration, it raised accuracy from 0.644 to 0.818 and hornet precision from 0.566 to 0.903; look-alikes called hornet fell from 133 to 20. That made it the single largest gain of the iteration.

Its two thresholds were chosen on calibration only, with a rule fixed beforehand: the most accurate pair with hornet recall ≥ 0.90 and precision ≥ 0.70. The pair is vth 0.2 (a hornet stays a hornet if the verifier gives it 0.2) and flip 0.6 (another class becomes a hornet if the verifier is 0.6 sure).

### Detector: v0.5 and v0.5b

The first v0.5 detector (YOLO26n, 20 epochs from COCO on 17,792 images) was much better on real photos but worse than v0.4 on synthetic entrance scenes: hornet recall 0.86 against 0.92, bee recall 0.90 against 0.93. Drawn scenes had dropped from 59 % of training images in v0.4 to 19 %.

A second synthetic set was added (seed 6, 25 % cutouts) and the model fine-tuned for 6 epochs. The result is v0.5b:

| Tier P v2 calibration (981 photos), with verifier | v0.5 | v0.5b |
|---|---|---|
| Accuracy | 0.895 | 0.883 |
| Hornet recall / precision | 0.907 / 0.904 | 0.887 / 0.899 |

| Tier S seed 7, node pipeline with verifier, v0.5 thresholds | v0.5 | v0.5b |
|---|---|---|
| Hornet recall / precision | 0.857 / 1.000 | 0.896 / 0.986 |
| Bee recall / precision | 0.898 / 0.973 | 0.916 / 0.977 |

**v0.5b was released.** On calibration the two differ by 12 photos of 981, within noise, while v0.5b is clearly better on the entrance scenes. Both were scored on the tier P v2 test, and both are reported: v0.5 reached accuracy 0.893 and hornet recall / precision 0.883 / 0.913, against v0.5b's 0.886 and 0.893 / 0.899. The choice was made before v0.5b's test was opened, and the test does not change it.

Detector thresholds were then lowered, because the verifier now guards hornet precision. They were tuned on synthetic scenes from seed 8, kept apart from the seed-7 test: bee 0.25 (from 0.35), hornet 0.30 (from 0.45), beetle 0.35 (from 0.5). On seed 8 this raised hornet recall from 0.877 to 0.923 and beetle recall from 0.59 to 0.69; going lower changed nothing.

### Stage 2: v0.5 classifier

The new YOLO26n-cls was compared with the v0.2 classifier behind the same v0.5 detector on the same scenes:

| | v0.2 classifier | v0.5 classifier |
|---|---|---|
| Recall | 0.916 | 0.881 |
| False positives on clean bees | 2.6 % | 1.8 % |
| Precision if 5 % of bees carry a mite | 0.65 | 0.73 |
| Precision if 2 % of bees carry a mite | 0.42 | 0.51 |

Real infestations sit at a few percent, where false positives decide precision, so v0.5's classifier was kept. With the final detector and thresholds its false-positive rate is 0.8 % (8 of 970 clean bees), which would give a precision of about 0.85 at 5 % prevalence.

### Results: tier P v2 test (1,612 photos, opened once per model)

| | v0.4 | v0.5 detector only | **v0.5 (released, with verifier)** |
|---|---|---|---|
| Accuracy | 0.652 | 0.854 | **0.886** |
| Hornet recall / precision | 0.748 / 0.570 | 0.857 / 0.859 | **0.893 / 0.899** |
| Bee recall / precision | 0.778 / 0.726 | 0.870 / 0.881 | **0.852 / 0.928** |
| Other-insect recall / precision | 0.480 / 0.685 | 0.839 / 0.824 | **0.907 / 0.838** |
| Look-alikes called "hornet" | 210 of 635 | 50 | **34** |

The "detector only" column is the first v0.5 detector; on top of it, the verifier adds 0.039 accuracy (0.854 to 0.893).

Look-alikes called "hornet", by group:

| Group (test photos) | v0.4 | v0.5 |
|---|---|---|
| *Vespula* (70) | 45 | 5 |
| *Polistes* (60) | 24 | 4 |
| *Dolichovespula* (50) | 23 | 2 |
| *Siricidae*, horntails (20) | 14 | 3 |
| *Volucella* hoverflies (30) | 11 | 1 |
| Other Vespidae (40) | 10 | 1 |
| Ants (20) | 9 | 2 |
| Robber flies (20) | 8 | 1 |
| Stingless bees (20) | 8 | 1 |
| *Sphecidae* (30) | 8 | 2 |
| Other hoverflies (30) | 7 | 2 |
| Hornet moth (15) | 6 | 1 |
| *Milesia* hoverflies (20) | 6 | 3 |
| Sap beetles (10) | 6 | 0 |
| *Scoliidae* (40) | 5 | 4 |
| All 23 groups (635) | 210 | 34 |

v0.5 confusion (rows: true class, columns: prediction): bee 426 / 12 hornet / 62 other; hornet 6 bee / 426 / 44 other / 1 none; other 24 bee / 34 hornet / 576 / 1 none. Missed hornets mostly become "other insect"; bees lost to "other" are the largest remaining error.

On the older tier P v1 test (600 photos), v0.5 reaches 0.862 (v0.4: 0.728), hornet recall / precision 0.840 / 0.923, 12 of 200 other insects called hornet.

### Results: tier S, the whole node pipeline

200 fresh full-resolution scenes (seed 7), ncnn models, operating thresholds, the verifier and stage 2, exactly as on the node:

| Measure | v0.4 | **v0.5** |
|---|---|---|
| Bee precision / recall | 0.935 / 0.932 | **0.956 / 0.932** |
| Hornet precision / recall | 1.000 / 0.922 | 0.973 / **0.935** |
| Scenes with a hornet in which one is found | 0.939 | 0.939 |
| Beetle precision / recall | 0.891 / 0.538 | 0.795 / **0.660** |
| Scenes with a beetle in which one is found | 0.736 | **0.830** |
| Other-insect precision / recall | 0.995 / 0.451 | 0.989 / **0.596** |
| Varroa on matched bees: precision / recall | 0.964 / 0.927 | **0.987** / 0.900 |
| Varroa false positives on clean bees | 2.5 % (24 of 972) | **0.8 % (8 of 970)** |
| Varroa rate: true / estimated | 41.3 % / 39.7 % | 41.1 % / 37.5 % |

At the synthetic prevalence (about 41 % of bees) the lower Varroa recall makes the rate estimate 3.6 points low. At real prevalence the false positives dominate, and there v0.5 is clearly better.

### Latency and memory (Raspberry Pi 3B, estimated)

Same method as for v0.4 ([`vision/bench.py`](../../vision/bench.py), anchored to ncnn's published Pi 3B+ timings, scaled to 1.2 GHz; `runs/bench_v0.5.json`):

| Model | Host, 4 threads | Pi 3B estimate, 4 threads | 1 thread |
|---|---|---|---|
| Stage 1, YOLO26n 320 | 11.4 ms | **251 ms** (166 to 405) | 318 ms |
| Stage 1b verifier, YOLO26n-cls 160, per candidate | 2.1 ms | **46 ms** (30 to 74) | 49 ms |
| Stage 2, YOLO26n-cls 128, per bee | 1.5 ms | **33 ms** (22 to 54) | 33 ms |
| Frame with 15 bees and one other insect | | **≈ 0.8 s** | |

Peak memory with all three models loaded and full frames processed: **173 MB** (budget 250 MB).

### What did not work, or not yet

- The first v0.5 detector lost ground on drawn entrance scenes when real photos became 80 % of training; v0.5b fixed most of it with a second synthetic set.
- Labeling with the prompt-free vocabulary alone: it finds bees but names them "squid".
- The first insectness classifier preferred partial bee boxes; partial boxes as negatives fixed it.
- Fork deadlocks: two of the new tools and one evaluation script hung when they forked a process pool after OpenCV or ncnn had started threads. Fixed by `cv2.setNumThreads(1)` before the fork, or one process per evaluation.

## Earlier iterations (v0.1 to v0.4)

### Setup (v0.1 to v0.4)

| | Stage 1 detector | Stage 2 Varroa classifier |
|---|---|---|
| Model | YOLO11n, COCO-pretrained, 2.59 M params, 1.6 GFLOPs at 320 px | YOLO11n-cls, ImageNet-pretrained, 2.81 M params, 0.13 GFLOPs at 128 px |
| Input | 640×480 frame letterboxed to 320 | 128×128 crop of a bee from the 1640×1232 frame |
| Classes | bee, hornet, shb, other_insect | clean, varroa |
| Training | CPU (4 cores, no GPU), batch 32, mosaic, 180° rotation, flips, HSV | CPU, batch 128, RandAugment, rotation, flips |
| Runtime on the node | ncnn, fp16 storage, 3 threads, no torch ([`vision/pipeline.py`](../../vision/pipeline.py)) | same |

A 30-epoch stage 1 run takes 1.5 hours on 3,400 synthetic scenes and 2 hours with the 2,333 real photos added; stage 2, about 50 minutes for 12 epochs.

### Iterations

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

#### Why v0.4 worked where v0.3 did not

v0.3 added more pasted cutouts of wasps and bumblebees; the model still learned "striped insect with a cutout edge on a board" and kept calling real wasps hornets. v0.4 shows the detector whole photos: the insect with its real lighting, focus and surroundings, and many real *Polistes* and *Vespula* wasps labeled `other_insect`. This is the cheap version of what a 3D render followed by a diffusion pass would try to buy. [ADR-0010](../adr/0010-real-photos-with-automatic-labels.md) compares the two.

The labels are automatic: the species comes from iNaturalist, the box from YOLOE text prompts ([`vision/pseudolabel.py`](../../vision/pseudolabel.py)), about 4 photos per second on the CPU. 2,333 of 3,900 photos got a confident box. A visual check of 15 random photos found 2 wrong boxes (a wild comb and a flower labeled "bee"), 1 partial box, and 2 photos with insects left unboxed.

#### Detector per class, tier S (v0.2 val, 600 scenes)

| Class | v0.2 mAP50 / mAP50-95 | v0.4 mAP50 / mAP50-95 |
|---|---|---|
| bee | 0.948 / 0.600 | 0.948 / 0.607 |
| hornet | 0.921 / 0.561 | 0.909 / 0.565 |
| shb | 0.684 / 0.282 | 0.681 / 0.285 |
| other_insect | 0.570 / 0.306 | 0.563 / 0.304 |
| all | 0.781 / 0.437 (P 0.834, R 0.710) | 0.775 / 0.440 (P 0.806, R 0.707) |

Stage 2 is the same in v0.2 and v0.4 (v0.2 val crops, 5,577 crops, 46 % with a visible mite): top-1 accuracy 0.877.

### Tier P: real photos (v0.1 to v0.4)

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

#### Caveat: photographers overlap

A few prolific observers took most of the iNaturalist hornet photos in the snapshot. Training pools and tier P share no photo and no observation, but they do share photographers: 94 % of the pool's hornet photos and about 70 % of its bee photos come from someone who also has a photo in tier P. Same photographer can mean the same camera, garden and style, which can make tier P look better than truly unseen photos. This applies to v0.2 (its cutouts come from the same pools) and to v0.4 alike, so the comparison between them is fair, but the absolute numbers may be somewhat optimistic. An observer-disjoint test would leave 8 hornets, too few to measure. A newer iNaturalist snapshot with more photographers would fix this (Jira EN-12).

### Tier S: the whole node pipeline (v0.2 and v0.4)

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

### Latency on the Raspberry Pi 3B (estimate, v0.2 and v0.4)

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

Targets from [training and evaluation](05-training-and-evaluation.md#acceptance-criteria). Release v0.5.

| Criterion | Target | v0.5 | Status |
|---|---|---|---|
| Hornet recall (tier P) | ≥ 0.90 | 0.893 image-level on tier P v2 test (v0.4: 0.748); 0.935 per hornet and 0.939 per scene on tier S | Not met by 0.007 on single photos; met on tier S |
| Hornet precision (tier P) | ≥ 0.70 | 0.899 on tier P v2 test (v0.4: 0.570) | **Met** |
| Bee detection recall (tier P) | ≥ 0.85 | Image-level bee recall 0.852 on tier P v2 test; 0.932 on tier S | Met image-level (boxes not scored in tier P) |
| Varroa crop recall / precision (tier P) | ≥ 0.75 / ≥ 0.70 | No real crops reachable; 0.900 / 0.987 on tier S, about 0.85 precision at 5 % prevalence | Not measurable on real crops |
| False threat events per day | ≤ 1 | Needs sequences in the generator | Not measured |
| Stage 1 latency p95 on the Pi | ≤ 1.0 s | ≈ 0.25 s estimated (up to 0.41 s) | Met, as an estimate |
| Frame with 15 bees on the Pi | ≤ 2.0 s | ≈ 0.8 s estimated | Met, as an estimate |
| Vision service memory | ≤ 250 MB | 173 MB peak with three models | Met |

## What the numbers do not show

- Entrance-camera performance (tier C/F). Needs the camera (Jira HW-01) and the field test (HW-04).
- Varroa on real bees. The public VarroaDataset (13.5k labeled real bee crops) is the next check, from a machine with Zenodo access (Jira US09).
- Small hive beetles on real images: 2 photos in the 2021 snapshot, 59 in the 2026 one. Tier S only.
- False alerts over time. The aggregation rule is unit-tested; its false-event rate needs synthetic sequences.

## Next iteration (v0.6), in order

1. **Real board backgrounds and team captures** from our camera (tier C): backgrounds for the generator, and 200 labeled frames to score the detector and verifier in the real domain (Jira EN-12).
2. **Hornet recall**: most missed hornets on photos become "other insect". Look at the calibration misses, then try a separate wasp class in the detector, or verifier rescues at a lower flip threshold, chosen on calibration.
3. **Sequences** in the generator, to measure false threat events per day and event-level hornet recall with the k-of-n rule.
4. **416 px stage 1** trial for small hive beetles, if the Pi budget allows.
5. **Varroa threshold** at realistic prevalence, and real Varroa data (VarroaDataset) from a machine that can reach Zenodo.
6. **Measure on the Pi**: replace every latency estimate with a measurement (Jira US11).

## Reproduce

```bash
# v0.5: snapshot, tier P v2 and pool; Open Images
python -m vision.inat filter --out data/raw/inat26 --taxa data/raw/inat/taxa.csv
python -m vision.inat v2 --src data/raw/inat26 --out data/raw/inat26_photos --exclude vision/splits/P-inat-v1.tsv data/raw/inat_pool/manifest.tsv data/raw/inat_pool2/manifest.tsv
python -m vision.openimages data/raw/openimages --out data/raw/oi-bees
# labeler: insectness classifier, benchmark against human boxes
python -m vision.insectness data/raw/oi-bees --out data/sim/C-insectness-v2
python -m vision.train stage2 data/sim/C-insectness-v2 --epochs 10 --name insectness-v2 --set model=yolo26n-cls.pt
python -m vision.labeler bench data/raw/oi-bees --insectness <insectness best.pt>
# labels, mosaics, cutouts, verifier, Open Images honeybees
python -m vision.pseudolabel data/raw/inat26_photos --insectness <insectness best.pt> --out data/sim/R-inat26-pseudo-v2
python -m vision.pseudolabel data/sim/R-inat26-pseudo-v2 --mosaics 3000 --out data/sim/R-inat26-mosaic-v2
python -m simulation.images.cutouts data/raw/inat26_photos data/assets/cutouts-v3 --insectness <insectness best.pt>
python -m vision.verifier data/sim/R-inat26-pseudo-v2 --out data/sim/C-verifier-v1
python -m vision.train stage2 data/sim/C-verifier-v1 --epochs 15 --name verifier-v1 --set model=yolo26n-cls.pt imgsz=160
python -m vision.openimages data/raw/oi-bees --verifier <verifier best.pt> --out data/sim/R-oi-bees-v1
# scenes and models
python -m simulation.images.compose --out data/sim/S-images-entrance-v0.5-s5 --n 4000 --seed 5 --cutouts data/assets/cutouts-v3 --real-frac 0.5 --dr-frac 0.15
python -m simulation.images.compose --out data/sim/S-images-entrance-v0.5-s6 --n 4000 --seed 6 --cutouts data/assets/cutouts-v3 --real-frac 0.25 --dr-frac 0.15
#   data/sim/M-v0.5/stage1/data.yaml: s5 scenes, labeled photos, mosaics, Open Images honeybees; M-v0.5b adds s6
python -m vision.train stage1 data/sim/M-v0.5 --epochs 20 --name s1-v0.5-yolo26n-320 --set model=yolo26n.pt
python -m vision.train stage1 data/sim/M-v0.5b --epochs 6 --name s1-v0.5b-yolo26n-320-ft --weights <v0.5 best.pt> --set optimizer=SGD lr0=0.002 lrf=0.2 warmup_epochs=0.5 close_mosaic=2
python -m vision.train stage2 data/sim/S-images-entrance-v0.5-s5 --epochs 12 --name s2-v0.5-yolo26n-cls-128 --set model=yolo26n-cls.pt
python -m vision.eval_real <detector best.pt> --tier P2 --split calib --verifier <verifier best.pt>
python -m vision.eval_system <stage1_ncnn_dir> <stage2_ncnn_dir> --n 200 --verifier <verifier_ncnn_dir>

# v0.1 to v0.4: pools disjoint from tier P v1
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
