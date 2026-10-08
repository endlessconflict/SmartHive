# vision/

Training, real-image evaluation, export and benchmarking of the two-stage pest detector, plus the torch-free inference pipeline the node runs.

Status: five iterations; v0.5 (YOLO26n detector, species verifier, Varroa classifier) is released in [`models/v0.5`](../models/v0.5/MODEL_CARD.md). Results and iterations: [docs/03-vision/07-results.md](../docs/03-vision/07-results.md).

| File | What it does |
|---|---|
| `train.py` | Stage 1 detector (320 px), stage 1b verifier and stage 2 classifier with project defaults; `--set model=yolo26n.pt` and `--weights` for fine-tuning |
| `inat.py` | Streams an iNaturalist metadata snapshot (`filter`), builds tier P v2 and the training pool with photographers kept apart (`v2`), CC0/CC-BY only |
| `openimages.py` | Open Images V7 photos with human bee boxes; keeps only honeybees with the verifier |
| `labeler.py`, `insectness.py` | Automatic boxes with OSI-licensed weights: prompt-free YOLOE proposals kept by our insect/background classifier; benchmark against human boxes ([ADR-0011](../docs/adr/0011-osi-clean-automatic-labeling.md)) |
| `verifier.py` | Dataset for the stage 1b species verifier (bee, hornet, other insect) from real and synthetic crops |
| `pseudolabel.py` | Real pool photos to detector training images (class from iNaturalist, boxes from `labeler.py`), and 3x3 mosaics at entrance scale ([ADR-0010](../docs/adr/0010-real-photos-with-automatic-labels.md)) |
| `splits/P-inat-v1.tsv`, `splits/P-inat-v2.tsv` | Frozen calib/test splits: class, group, SHA-256, license, source URL, observer |
| `eval_real.py` | Image-level evaluation on real photos (tier P v1 or v2), optionally with the verifier |
| `export.py` | PyTorch to ncnn |
| `pipeline.py` | Node runtime: ncnn only (no torch): stage 1, stage 1b verifier, crops, stage 2, motion gate, k-of-n aggregation, Varroa index with Wilson interval |
| `bench.py` | Latency here, and a Raspberry Pi 3B estimate anchored to ncnn's published Pi benchmarks |

```bash
python -m simulation.images.compose --out data/sim/S-images-entrance-v0.1-s1 --n 4000 --seed 1
python -m vision.train stage1 data/sim/S-images-entrance-v0.1-s1 --epochs 30
python -m vision.train stage2 data/sim/S-images-entrance-v0.1-s1 --epochs 15
python -m vision.eval_real runs/detect/runs/stage1/<run>/weights/best.pt --split calib
python -m vision.export runs/detect/runs/stage1/<run>/weights/best.pt --imgsz 320
python -m vision.bench <ncnn_dir>:320 <ncnn_dir>:128
```

Pretrained checkpoints (`yolo11n.pt`, `yolo11n-cls.pt`) go in `data/weights/`. Datasets, runs and weights are not committed.

Owner: Adrien Cubilla.
