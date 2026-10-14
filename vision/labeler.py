"""Insect boxes for automatic labeling, with OSI-licensed weights only (ADR-0011).

YOLOE prompt-free checkpoints carry their own vocabulary, so no text encoder is loaded. (Text prompts
load Apple's MobileCLIP, whose weights are research-only.) Their boxes are good but their names are not
(Open Images bees come out as "squid" or "wood duck"; keeping only insect words found at most 25 % of
the bees), so the boxes are kept class-agnostic and our insectness classifier decides. The species
comes from elsewhere (iNaturalist identification, Open Images label).

    python -m vision.labeler bench data/raw/oi-bees --insectness <best.pt>   # against human boxes
"""
import argparse
import json
from pathlib import Path

import cv2

WEIGHTS = Path("data/weights")


class Labeler:
    """Prompt-free YOLOE proposals, kept when the insectness classifier (vision/insectness.py) says insect."""

    def __init__(self, insectness: Path, pf="yoloe-26l-seg-pf.pt", threads=4, size=128):
        import torch
        from ultralytics import YOLO, YOLOE
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
        return _dedup([b for b in self.score(img, props if props is not None else proposals(self.pf, img)) if b[4] >= min_p])


def contains(a, b, frac=0.9):
    """b lies (almost) inside a: a part of an insect boxed separately, or a box around several."""
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix >= frac * (b[2] - b[0]) * (b[3] - b[1])


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / max(1e-9, (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)


def bench(folder: Path, insectness: Path, thresholds=(0.5, 0.7, 0.8, 0.9, 0.95)):
    """Score the labeler against Open Images human bee boxes on images kept out of insectness training
    (validation and test splits). All bees in these images are boxed; other insects are not, so a few
    "false positives" may be real insects."""
    import csv
    from vision.insectness import gt_boxes
    held = [r["file"] for r in csv.DictReader(open(folder / "manifest.tsv"), delimiter="\t") if r["split"] != "train"]
    props = json.loads((folder / "proposals-yoloe-26l-seg-pf.json").read_text())
    lab = Labeler(insectness)
    scored = {}
    for name in held:
        img = cv2.imread(str(folder / "images" / name))
        h, w = img.shape[:2]
        scored[name] = (gt_boxes(folder, folder / "images" / name, w, h), lab.score(img, props[name]), img)
    out = {"images": len(held), "gt_boxes": sum(len(g) for g, _, _ in scored.values()),
           "proposal_recall_iou50": round(sum(max((iou(p, g) for p in ps), default=0) >= 0.5 for g_, ps, _ in scored.values() for g in g_)
                                          / max(1, sum(len(g) for g, _, _ in scored.values())), 3)}
    for th in thresholds:
        tp = fp = fn = 0
        for gts, ps, img in scored.values():
            pred = _dedup([p for p in ps if p[4] >= th])
            used = set()
            for p in pred:
                best, j = max(((iou(p, g), k) for k, g in enumerate(gts) if k not in used), default=(0, None))
                if best >= 0.5:
                    used.add(j)
                    tp += 1
                else:
                    fp += 1
            fn += len(gts) - len(used)
        out[f"p>={th}"] = {"precision": round(tp / max(1, tp + fp), 3), "recall": round(tp / max(1, tp + fn), 3)}
    return out


def _dedup(scored):
    keep = []
    for b in sorted(scored, key=lambda b: -b[4]):
        if all(iou(b, k) < 0.5 and not contains(k, b) and not contains(b, k) for k in keep):
            keep.append(b)
    return keep


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["bench"])
    ap.add_argument("folder", type=Path)
    ap.add_argument("--insectness", type=Path, required=True)
    a = ap.parse_args()
    res = bench(a.folder, a.insectness)
    (a.folder / "labeler_bench.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
