"""Real photos with automatic labels: iNaturalist photos become detector training images.

The species comes from iNaturalist (research-grade identification), the boxes from vision/labeler.py:
prompt-free YOLOE proposals kept by the insectness classifier (ADR-0011). One observation is one
species, so every insect box in a photo gets the photo's class. Pools come from vision/inat.py v2,
which keeps photos, observations and photographers of tier P v2 out of training.

    python -m vision.pseudolabel data/raw/inat26_photos --insectness <best.pt> --out data/sim/R-inat26-pseudo-v2

v0.4 used YOLOE text prompts instead (R-inat-pseudo-v1); they load a research-only text encoder.
"""
import argparse
import csv
import json
import random
from pathlib import Path

import cv2
import numpy as np

from vision.insectness import cached_proposals
from vision.labeler import Labeler, iou

CLASSES = ["bee", "hornet", "shb", "other_insect"]


def yolo_line(cls, box, w, h):
    x0, y0, x1, y1 = box
    return f"{cls} {(x0 + x1) / 2 / w:.6f} {(y0 + y1) / 2 / h:.6f} {(x1 - x0) / w:.6f} {(y1 - y0) / h:.6f}"


def tidy(boxes, w, h, rel_area=0.1, min_area=0.0015, dup_iou=0.3):
    """One observation shows insects of one species at a similar size: drop boxes far smaller than the
    largest (a rock, a fingertip) or tiny in the photo, and near-duplicates. From a visual audit of v2."""
    area = lambda b: (b[2] - b[0]) * (b[3] - b[1])
    if not boxes:
        return []
    big = max(area(b) for b in boxes)
    keep = []
    for b in boxes:  # already sorted by insect probability
        if area(b) >= max(rel_area * big, min_area * w * h) and all(iou(b, k) < dup_iou for k in keep):
            keep.append(b)
    return keep


def main(pool: Path, insectness: Path, out: Path, min_p=0.7, max_boxes=8, threads=4):
    rows = [r for r in csv.DictReader(open(pool / "manifest.tsv"), delimiter="\t") if r["cls"] in CLASSES]
    lab = Labeler(insectness, threads=threads)
    props = cached_proposals(lab.pf, [pool / r["file"] for r in rows], pool / "proposals-yoloe-26l-seg-pf.json")
    (out / "images/train").mkdir(parents=True, exist_ok=True)
    (out / "labels/train").mkdir(parents=True, exist_ok=True)
    stats = {"photos": len(rows), "no_insect": 0, "kept": {}, "boxes": 0}
    credits = []
    for r in rows:
        f = pool / r["file"]
        img = cv2.imread(str(f))
        h, w = img.shape[:2]
        bs = tidy(lab(img, min_p=min_p, props=props[f.name]), w, h)[:max_boxes]
        if not bs:
            stats["no_insect"] += 1
            continue
        name = f"{r['cls']}_{f.stem}"
        cv2.imwrite(str(out / "images/train" / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        (out / "labels/train" / f"{name}.txt").write_text("\n".join(yolo_line(CLASSES.index(r["cls"]), b[:4], w, h) for b in bs) + "\n")
        stats["kept"][r["cls"]] = stats["kept"].get(r["cls"], 0) + 1
        stats["boxes"] += len(bs)
        credits.append({"file": f"{name}.jpg", **{k: r[k] for k in ("cls", "group", "taxon_id", "license", "source_url", "observer_id")}})
    with open(out / "manifest.tsv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, list(credits[0]), delimiter="\t", lineterminator="\n")
        wr.writeheader()
        wr.writerows(credits)
    (out / "stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats))


def mosaics(src: Path, out: Path, n: int, grid=(3, 3), size=(640, 480), seed=0, min_px=4):
    """Real insects at entrance scale: each image tiles grid photos of a labeled set (images/ + labels/),
    so an insect that filled a photo becomes 20 to 100 px, close to what the 320 px detector sees."""
    imgs = sorted((src / "images/train").glob("*.jpg"))
    rng = random.Random(seed)
    (out / "images/train").mkdir(parents=True, exist_ok=True)
    (out / "labels/train").mkdir(parents=True, exist_ok=True)
    tw, th = size[0] // grid[0], size[1] // grid[1]
    for k in range(n):
        canvas = np.full((size[1], size[0], 3), 114, np.uint8)
        lines = []
        for t, f in enumerate(rng.sample(imgs, grid[0] * grid[1])):
            img = cv2.imread(str(f))
            h, w = img.shape[:2]
            s = min(tw / w, th / h)
            nw, nh = max(1, int(w * s)), max(1, int(h * s))
            ox, oy = (t % grid[0]) * tw + (tw - nw) // 2, (t // grid[0]) * th + (th - nh) // 2
            canvas[oy:oy + nh, ox:ox + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
            for l in open(src / "labels/train" / f"{f.stem}.txt"):
                c, x, y, bw, bh = l.split()
                bw, bh = float(bw) * nw, float(bh) * nh
                if max(bw, bh) >= min_px:
                    lines.append(f"{c} {(ox + float(x) * nw) / size[0]:.6f} {(oy + float(y) * nh) / size[1]:.6f} {bw / size[0]:.6f} {bh / size[1]:.6f}")
        cv2.imwrite(str(out / "images/train" / f"mosaic_{k:05d}.jpg"), canvas, [cv2.IMWRITE_JPEG_QUALITY, 92])
        (out / "labels/train" / f"mosaic_{k:05d}.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pool", type=Path)
    ap.add_argument("--insectness", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--min-p", type=float, default=0.7)  # Open Images held-out: precision 0.65, recall 0.65 at IoU 0.5
    ap.add_argument("--mosaics", type=int, help="instead of labeling: build this many 3x3 mosaics from the labeled set in pool")
    a = ap.parse_args()
    if a.mosaics:  # python -m vision.pseudolabel data/sim/R-inat26-pseudo-v2 --mosaics 3000 --out data/sim/R-inat26-mosaic-v2
        mosaics(a.pool, a.out, a.mosaics)
    else:
        main(a.pool, a.insectness, a.out, a.min_p)
