"""Species verifier (stage 1b): a second look at every non-bee detection, on a full-resolution crop.

The detector sees the whole frame at 320 px, where a hornet and a Vespula wasp differ by a few pixels.
The verifier sees the insect alone at 160 px from the 1640x1232 frame and was trained mostly on real
photos of exactly the insects that get confused: hornets against Vespula, Polistes, Dolichovespula,
Scoliidae, hornet-mimic hoverflies and moths, bumblebees and other bees. Hornet and beetle candidates
are rare at an entrance, so its cost on the Pi is a few crops per hour, not per frame.

Training crops (classes bee, hornet, other_insect):
- real: every box of the auto-labeled iNaturalist pool (vision/pseudolabel.py); photographers in hash
  bucket 9 go to validation;
- synthetic: insects cropped from fresh full-resolution entrance scenes, for the top-down view.

    python -m vision.verifier data/sim/R-inat26-pseudo-v2 --out data/sim/C-verifier-v1
    python -m vision.train stage2 data/sim/C-verifier-v1 --epochs 15 --name verifier-v1 --set model=yolo26n-cls.pt imgsz=160
"""
import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np

from vision.inat import bucket
from vision.pipeline import crop

CLASSES = ["bee", "hornet", "other_insect"]
YOLO_CLASSES = ["bee", "hornet", "shb", "other_insect"]


def build(real: Path, out: Path, size=160, n_scenes=1500, seed=5, workers=3):
    for s in ("train", "val"):
        for c in CLASSES:
            (out / "stage2" / s / c).mkdir(parents=True, exist_ok=True)
    n = {"real": {}, "synthetic": {}}
    for r in csv.DictReader(open(real / "manifest.tsv"), delimiter="\t"):
        if r["cls"] not in CLASSES:
            continue
        s = "val" if bucket(r["observer_id"]) == 9 else "train"
        img = cv2.imread(str(real / "images/train" / r["file"]))
        h, w = img.shape[:2]
        for k, l in enumerate(open(real / "labels/train" / (Path(r["file"]).stem + ".txt"))):
            _, x, y, bw, bh = map(float, l.split())
            box = ((x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h)
            cv2.imwrite(str(out / "stage2" / s / r["cls"] / f"{Path(r['file']).stem}_{k}.jpg"), crop(img, box, size=size))
            n["real"][r["cls"]] = n["real"].get(r["cls"], 0) + 1
    from simulation.images import compose
    rng = np.random.default_rng(seed)
    for s, lib_seed in (("train", seed), ("val", seed + 1)):
        lib = compose.build_library(s, lib_seed, workers)
        for i in range(n_scenes if s == "train" else n_scenes // 5):
            frame, labels, _ = compose.scene(200_000 + i, lib_seed, lib)
            for k, lb in enumerate(labels):
                c = lb["cls"]
                if c not in CLASSES or lb["visible"] < 0.5 or (c == "bee" and rng.random() > 0.15):
                    continue  # bees are most of every scene; keep the classes balanced
                cv2.imwrite(str(out / "stage2" / s / c / f"syn_{s}_{i}_{k}.jpg"), cv2.cvtColor(crop(frame, lb["box"], size=size), cv2.COLOR_RGB2BGR))
                n["synthetic"][c] = n["synthetic"].get(c, 0) + 1
    (out / "stats.json").write_text(json.dumps(n, indent=2))
    print(n)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("real", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    build(a.real, a.out)
