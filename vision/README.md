# vision/

Training, real-image evaluation, export and benchmarking of the two-stage pest detector, plus the torch-free inference pipeline the node runs.

Status: four iterations; v0.4 (synthetic scenes plus auto-labeled real photos) is released in [`models/v0.4`](../models/v0.4/MODEL_CARD.md). Results and iterations: [docs/03-vision/07-results.md](../docs/03-vision/07-results.md).

| File | What it does |
|---|---|
| `train.py` | Stage 1 (YOLO11n detector, 320 px) and stage 2 (YOLO11n-cls Varroa classifier, 128 px) with project defaults |
| `inat.py` | Builds the tier P check set and the disjoint training pools from the iNaturalist Open Dataset (CC0/CC-BY only) |
| `pseudolabel.py` | Real pool photos to detector training images: class from iNaturalist, box from YOLOE ([ADR-0010](../docs/adr/0010-real-photos-with-automatic-labels.md)) |
| `splits/P-inat-v1.tsv` | Frozen calib/test split: class, SHA-256, license, source URL, observer |
| `eval_real.py` | Image-level evaluation of a detector on real iNaturalist photos |
| `export.py` | PyTorch to ncnn |
| `pipeline.py` | Node runtime: ncnn only (no torch): stage 1, crops, stage 2, motion gate, k-of-n aggregation, Varroa index with Wilson interval |
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
