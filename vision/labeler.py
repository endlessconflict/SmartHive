"""Insect boxes for automatic labeling, with OSI-licensed weights only (ADR-0011).

YOLOE prompt-free checkpoints carry their own vocabulary, so no text encoder is loaded. (Text prompts
load Apple's MobileCLIP, whose weights are research-only.) Only insect words of that vocabulary count;
the species comes from elsewhere (iNaturalist identification, Open Images label).

    python -m vision.labeler bench data/raw/oi-bees --n 300      # recall/precision against human boxes
"""
import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLOE

WEIGHTS = Path("data/weights")
INSECT_WORDS = {"insect", "bee", "bumblebee", "hornet", "wasp", "fly", "ant", "beetle", "bug", "moth", "mantid", "cicada",
                "cockroach", "ladybug", "grasshopper", "cricket", "dragonfly", "housefly", "mosquito", "termite", "firefly",
                "hoverfly", "honeybee", "yellow jacket", "stinkbug", "weevil", "caterpillar", "butterfly"}


class Labeler:
    """Prompt-free YOLOE proposals, kept when the insectness classifier (vision/insectness.py) says insect."""

    def __init__(self, insectness: Path, pf="yoloe-26l-seg-pf.pt", threads=4, size=128):
        from ultralytics import YOLO
        torch.set_num_threads(threads)
        self.pf = YOLOE(str(WEIGHTS / pf))
        self.cls = YOLO(str(insectness))
        self.k = next(i for i, n in self.cls.names.items() if n == "insect")
        self.size = size

    def score(self, img, props):
        from vision.pipeline import crop
        if not props:
            return []
        crops = [crop(img, p[:4], pad=0.15, size=self.size) for p in props]
        probs = [float(r.probs.data[self.k]) for r in self.cls.predict(crops, imgsz=self.size, verbose=False, device="cpu")]
        return [(*p[:4], q) for p, q in zip(props, probs)]

    def __call__(self, img, min_p=0.5, props=None):
        """Insect boxes [(x0, y0, x1, y1, p_insect)], overlapping duplicates removed."""
        from vision.insectness import proposals
        scored = sorted((b for b in self.score(img, props if props is not None else proposals(self.pf, img)) if b[4] >= min_p),
                        key=lambda b: -b[4])
        keep = []
        for b in scored:
            if all(iou(b, k) < 0.5 and not contains(k, b) and not contains(b, k) for k in keep):
                keep.append(b)
        return keep


def contains(a, b, frac=0.9):
    """b lies (almost) inside a: a part of an insect boxed separately, or a box around several."""
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix >= frac * (b[2] - b[0]) * (b[3] - b[1])


class InsectBoxes:
    def __init__(self, weights="yoloe-26l-seg-pf.pt", conf=0.05, threads=4):
        torch.set_num_threads(threads)
        self.model = YOLOE(str(WEIGHTS / weights))
        self.keep = [i for i, n in self.model.names.items() if n.lower() in INSECT_WORDS]
        self.conf = conf

    def __call__(self, img, rel=0.5, min_other=0.3):
        """The most confident insect plus others nearly as confident: [(x0, y0, x1, y1, conf), ...]."""
        r = self.model.predict(img, conf=self.conf, classes=self.keep, agnostic_nms=True, verbose=False, device="cpu")[0]
        if not len(r.boxes):
            return []
        top = float(r.boxes.conf.max())
        return [(*b.tolist(), float(c)) for b, c in zip(r.boxes.xyxy, r.boxes.conf)
                if float(c) >= max(min_other, rel * top) or float(c) == top]


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / max(1e-9, (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)


def bench(folder: Path, n: int, weights: list[str]):
    """Score labelers against Open Images human bee boxes (all bees in these images are boxed)."""
    files = sorted((folder / "images").glob("*.jpg"))[:n]
    gt = {}
    for f in files:
        img = cv2.imread(str(f))
        h, w = img.shape[:2]
        gt[f] = [((x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h)
                 for x, y, bw, bh in (map(float, l.split()[1:]) for l in open(folder / "labels" / f"{f.stem}.txt"))]
    out = {}
    for wname in weights:
        lab = InsectBoxes(wname)
        tp = fp = fn = 0
        ious, t0 = [], time.time()
        for f in files:
            pred = lab(cv2.imread(str(f)))
            used = set()
            for p in sorted(pred, key=lambda p: -p[4]):
                best, j = max(((iou(p, g), k) for k, g in enumerate(gt[f]) if k not in used), default=(0, None))
                if best >= 0.5:
                    used.add(j)
                    tp += 1
                    ious.append(best)
                else:
                    fp += 1
            fn += len(gt[f]) - len(used)
        out[wname] = {"images": len(files), "precision": round(tp / max(1, tp + fp), 3), "recall": round(tp / max(1, tp + fn), 3),
                      "mean_iou_matched": round(float(np.mean(ious)), 3) if ious else 0, "s_per_image": round((time.time() - t0) / len(files), 2)}
        print(wname, out[wname], flush=True)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["bench"])
    ap.add_argument("folder", type=Path)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--weights", nargs="+", default=["yoloe-26s-seg-pf.pt", "yoloe-26l-seg-pf.pt", "yoloe-11l-seg-pf.pt"])
    a = ap.parse_args()
    res = bench(a.folder, a.n, a.weights)
    (a.folder / "labeler_bench.json").write_text(json.dumps(res, indent=2))
