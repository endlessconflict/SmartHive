"""Is this box an insect? A small crop classifier that turns prompt-free YOLOE boxes into insect boxes.

Prompt-free YOLOE finds 82 % of Open Images' human-boxed bees at IoU 0.5, but names them "squid" or
"wood duck", so its class is useless and its boxes include flowers and leaves. This classifier decides
which boxes hold an insect; the species comes from iNaturalist. All weights involved are OSI-licensed.

Training crops:
- insect: Open Images human bee boxes (train split images) and procedural hornets, wasps, flies, ants,
  beetles and bees pasted on real background patches, so "insect" does not collapse into "bee";
- background: prompt-free boxes in the same Open Images photos that overlap no bee (IoU < 0.1).
Open Images validation and test images stay out, to score the whole labeler (vision/labeler.py).

    python -m vision.insectness data/raw/oi-bees --out data/sim/C-insectness-v1
    python -m vision.train stage2 data/sim/C-insectness-v1 --epochs 10 --name insectness-v1 --set model=yolo26n-cls.pt
"""
import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np

from simulation.images import compose
from vision.labeler import iou
from vision.pipeline import crop

PF = "yoloe-26l-seg-pf.pt"


def proposals(model, img, conf=0.01, max_det=50):
    """Class-agnostic boxes from the prompt-free model."""
    r = model.predict(img, conf=conf, agnostic_nms=True, max_det=max_det, verbose=False, device="cpu")[0]
    return [(*b.tolist(), float(c)) for b, c in zip(r.boxes.xyxy, r.boxes.conf)]


def cached_proposals(model, files, cache: Path):
    done = json.loads(cache.read_text()) if cache.exists() else {}
    for k, f in enumerate(files):
        if f.name not in done:
            done[f.name] = proposals(model, cv2.imread(str(f)))
        if k % 200 == 0:
            cache.write_text(json.dumps(done))
    cache.write_text(json.dumps(done))
    return done


def gt_boxes(folder: Path, f: Path, w, h):
    return [((x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h)
            for x, y, bw, bh in (map(float, l.split()[1:]) for l in open(folder / "labels" / f"{f.stem}.txt"))]


def paste_sprite(rng, bg, sprite):
    """A procedural insect (RGBA) on a real background patch, filling 40 to 80 % of the crop."""
    s = bg.shape[0]
    rgba = sprite["rgba"]
    k = rng.uniform(0.4, 0.8) * s / max(rgba.shape[:2])
    rgba = cv2.resize(rgba, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    M = cv2.getRotationMatrix2D((rgba.shape[1] / 2, rgba.shape[0] / 2), rng.uniform(0, 360), 1)
    rgba = cv2.warpAffine(rgba, M, (rgba.shape[1], rgba.shape[0]))
    y0, x0 = (s - rgba.shape[0]) // 2, (s - rgba.shape[1]) // 2
    a = rgba[..., 3:4].astype(np.float32) / 255
    out = bg.copy().astype(np.float32)
    region = out[max(0, y0):y0 + rgba.shape[0], max(0, x0):x0 + rgba.shape[1]]
    src = rgba[max(0, -y0):max(0, -y0) + region.shape[0], max(0, -x0):max(0, -x0) + region.shape[1]]
    aa = a[max(0, -y0):max(0, -y0) + region.shape[0], max(0, -x0):max(0, -x0) + region.shape[1]]
    region[:] = src[..., 2::-1] * aa + region * (1 - aa)  # sprites are RGB, backgrounds BGR
    return out.astype(np.uint8)


def main(oi: Path, out: Path, seed=0, size=128, neg_per_image=6, workers=3):
    from ultralytics import YOLOE
    rng = np.random.default_rng(seed)
    split_of = {r["file"]: ("train" if r["split"] == "train" else "val") for r in csv.DictReader(open(oi / "manifest.tsv"), delimiter="\t")}
    files = sorted(f for f in (oi / "images").glob("*.jpg") if f.name in split_of)
    props = cached_proposals(YOLOE(str(Path("data/weights") / PF)), files, oi / f"proposals-{PF}.json")
    for s in ("train", "val"):
        for c in ("insect", "background"):
            (out / "stage2" / s / c).mkdir(parents=True, exist_ok=True)
    bgs = {"train": [], "val": []}
    n = {"insect": 0, "background": 0, "synthetic": 0}
    for f in files:
        s = split_of[f.name]
        img = cv2.imread(str(f))
        h, w = img.shape[:2]
        gts = gt_boxes(oi, f, w, h)
        for k, g in enumerate(gts):
            cv2.imwrite(str(out / "stage2" / s / "insect" / f"{f.stem}_{k}.jpg"), crop(img, g, pad=rng.uniform(0.05, 0.3), size=size))
            n["insect"] += 1
        negs = [p for p in props[f.name] if max((iou(p, g) for g in gts), default=0) < 0.1]
        for k in rng.permutation(len(negs))[:neg_per_image]:
            c = crop(img, negs[k][:4], pad=0.15, size=size)
            cv2.imwrite(str(out / "stage2" / s / "background" / f"{f.stem}_n{k}.jpg"), c)
            bgs[s].append(c)
            n["background"] += 1
    for s, lib_seed in (("train", seed + 1), ("val", seed + 2)):
        lib = [sp for sp in compose.build_library(s, lib_seed, workers) if sp["cls"] != "bee" or rng.random() < 0.3]
        for k, sp in enumerate(lib):
            img = paste_sprite(rng, bgs[s][rng.integers(len(bgs[s]))], sp)
            cv2.imwrite(str(out / "stage2" / s / "insect" / f"syn_{sp['cls']}_{k}.jpg"), img)
            n["synthetic"] += 1
    (out / "stats.json").write_text(json.dumps(n, indent=2))
    print(n)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("oi", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    main(a.oi, a.out)
