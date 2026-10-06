# Training and evaluation

Status: Implemented for v0.1. Numbers live in [07-results.md](07-results.md).

Owner: Adrien Cubilla

## Principle

A model trained on synthetic images will always score well on more synthetic images from the same generator. That number says the training worked; it says nothing about bees. Every result in this project is reported per data tier (S, P, C, F; see [data strategy](../04-data/01-data-problem-and-strategy.md#four-data-tiers)), and the one that counts for the real world is train-on-synthetic, test-on-real.

## Data splits

| Split | Tier | Content | Used for |
|---|---|---|---|
| `train` | S | Synthetic images and crops | Fitting weights |
| `val-syn` | S | Synthetic, generated with a different seed and a held-out subset of assets (cutouts and backgrounds not used in `train`) | Early stopping, threshold tuning, debugging |
| `val-real` | P (calibration) | `calib` half of [`P-inat-v1`](../../vision/splits/P-inat-v1.tsv): 200 bee, 200 hornet, 200 other-insect photos | Choosing between generator versions and model variants |
| `test-real` | P (test) | `test` half of `P-inat-v1`, same sizes, SHA-256 per file | Final numbers per milestone, opened once |
| `test-field` | C / F | Team captures and demo hive frames, hand-labeled | Domain gap report and demo |

Holding out assets in `val-syn` matters: if the same bee photo appears in train and validation, even at a different position and lighting, validation overestimates performance. The proposal already warned against nearly identical images and frames from one temporal sequence crossing splits. For public data, split by source video or recording session, never by frame.

## How the tier P test works

The iNaturalist photos have species labels but no boxes, and the insect can fill the frame or be a speck. [`vision/eval_real.py`](../../vision/eval_real.py) therefore runs an **image-level** test:

1. Letterbox each photo into a 640 px square at three scales (long side 640, 320 and 160 px). The smallest one puts a bee at roughly the size it has on our entrance camera.
2. Run the stage 1 detector on all three at its training input size (320).
3. The most confident detection across the three names the photo. No detection at all counts as `none`.
4. Report accuracy over bee/hornet/other (chance is 33 %), recall per class, how often anything is detected, and the confusion matrix.

This measures whether insects drawn by our renderer teach the model what real bees and hornets look like. It does not measure entrance-camera performance (no boards, no crowding, varied viewpoints). That needs tier C/F images from our own camera. Small hive beetle (2 photos) and Varroa (10 photos, mostly close-ups of mites, not bee crops) cannot be scored with this set.

## System-level test on synthetic scenes

[`vision/eval_system.py`](../../vision/eval_system.py) runs the exported ncnn models through the node pipeline itself ([`vision/pipeline.py`](../../vision/pipeline.py)), on full-resolution scenes generated fresh from the validation sprite library. It reports per-class precision and recall at IoU 0.5 with the operating thresholds, scene-level recall for hornets and beetles, Varroa precision and recall on matched walking bees, the true versus estimated Varroa rate, and time per frame. This is tier S, but it is the only test that covers both stages, the crop geometry and the thresholds together.

## Training recipe (stage 1)

| Setting | Starting value |
|---|---|
| Initialization | COCO-pretrained weights |
| Input | 320 (then 416 as an experiment) |
| Epochs | 100 to 150 on v1.0 data, with early stopping on `val-syn` mAP |
| Augmentation | Framework defaults (mosaic, HSV, flips, scale) plus our camera effects already baked into the data. Mosaic off for the last 10 epochs |
| Class balance | Generator oversamples pests; check per-class counts in the dataset card |
| Compute | Laptop CPU for smoke tests; any free GPU the team has access to for full runs |

## Training recipe (stage 2)

| Setting | Starting value |
|---|---|
| Initialization | ImageNet-pretrained MobileNetV3-Small, or from scratch for the custom CNN |
| Input | 128 × 128 crops |
| Loss | Binary cross-entropy, with class weights or focal loss if the positive share is small |
| Balance | About 30 % positives in training, with many look-alike negatives (pollen, dark bands, debris) |
| Augmentation | Small rotations, color jitter, blur, JPEG; random erasing that never removes a labeled mite entirely |

## Metrics

### Stage 1

| Metric | Why |
|---|---|
| Precision, recall, F1 per class at the chosen threshold | What the system will actually do |
| mAP@50 and mAP@50:95 per class | Standard comparison, as in the proposal |
| Recall on `hornet` and `shb` | A miss means no alert; the proposal makes this the priority |
| Metrics by object size and blur bucket | Shows where the generator or the model is weak |

### Stage 2

| Metric | Why |
|---|---|
| Precision, recall, F1 for `varroa` | Per crop |
| ROC-AUC and PR-AUC | Threshold-free comparison between models |
| Recall by mite visibility and blur | From synthetic metadata |
| False positive rate on look-alike negatives (pollen, debris) | The failure mode most likely to annoy a beekeeper |

### System level (after aggregation)

| Metric | How |
|---|---|
| Event recall | Share of threat episodes (in synthetic sequences and any real clips) that produce an event |
| False events per day | On sequences with no pests, at realistic traffic |
| Varroa index error | Absolute difference between estimated and true index on synthetic sequences with known infection rate |
| Latency | Frame to event on the Pi |

### Edge

| Metric | How |
|---|---|
| Inference time per stage, p50 and p95 | On the Pi 3B, with the full node software running |
| Analyzed frames per second | End to end |
| Peak memory (RSS) of the vision service | Must stay under its systemd limit |
| Energy per analyzed frame | With an INA219 or USB power meter |
| Accuracy loss from INT8 | FP32 vs INT8 on `val-real` |

## The sim-to-real protocol

At every milestone:

1. Train on the current synthetic version.
2. Report on `val-syn` (sanity) and `val-real` (what matters).
3. Gap = metric on `val-syn` minus metric on `val-real`. Track it over generator versions. A shrinking gap with a rising `val-real` is progress; a rising `val-syn` alone is not.
4. Inspect the 50 worst `val-real` errors, label each with a cause (scale, blur, lighting, look-alike, unseen pose, unseen background, label noise), and turn the most common cause into the next generator change.
5. Optional experiment: fine-tune on a small amount of real data (if licenses allow training use) and report how much it closes the gap. Dwibedi et al. found that adding about 10 % real data to synthetic data can match training on real data only. If that holds for us, it is the strongest argument for collecting even a few hundred labeled field images.

## Acceptance criteria

EL-26 asks the client for minimum values. Until they answer, these are the team's proposed targets for the Prototype 1 demo. They are deliberately modest, because real-image evaluation data is limited and the camera is not chosen yet.

| Metric | Tier | Target |
|---|---|---|
| Hornet recall at the operating threshold | P test | ≥ 0.90 |
| Hornet precision | P test | ≥ 0.70 |
| Bee detection recall (stage 1) | P test | ≥ 0.85 |
| Varroa crop recall | P test (VarroaDataset or equivalent) | ≥ 0.75 |
| Varroa crop precision | P test | ≥ 0.70 |
| False threat events per day | Synthetic no-pest sequences | ≤ 1 |
| Stage 1 latency, p95 | Pi 3B | ≤ 1.0 s |
| Full analysis of a frame with 15 bees, p95 | Pi 3B | ≤ 2.0 s |
| Vision service memory | Pi 3B | ≤ 250 MB |

For context, Bilik et al. (2021) report F1 up to 0.874 for infected bees and 0.714 for individual mites with YOLO and SSD trained on 600 real images. Small hive beetle has no target yet: there is too little real data to test it credibly, and that should be stated plainly at the demo.

## Experiment tracking

Every training run logs to MLflow: dataset ID, generator commit, model config, metrics per split, and the exported artifact. Results tables in reports are generated from MLflow, not typed by hand.
