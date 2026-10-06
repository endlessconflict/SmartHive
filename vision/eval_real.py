"""Tier P check: does a detector trained only on procedural insects recognise real ones?

iNaturalist photos have no boxes and no fixed scale, so this is an image-level test: each photo
is letterboxed at three scales (insect large, medium, entrance-camera small), the detector runs on
all three, and the most confident detection names the photo. Classes without enough photos
(shb: 2, varroa: 10) are reported but not scored.

    python -m vision.eval_real runs/stage1/<run>/weights/best.pt --split calib
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

ROOT = Path("data/raw/inat")
SCORED = ["bee", "hornet", "other_insect"]
SCALES = (640, 320, 160)


def letterbox(img, side, canvas=640):
    h, w = img.shape[:2]
    k = side / max(h, w)
    small = cv2.resize(img, (max(1, int(w * k)), max(1, int(h * k))), interpolation=cv2.INTER_AREA)
    out = np.full((canvas, canvas, 3), 114, np.uint8)
    y, x = (canvas - small.shape[0]) // 2, (canvas - small.shape[1]) // 2
    out[y:y + small.shape[0], x:x + small.shape[1]] = small
    return out


def evaluate(weights, split, imgsz, conf=0.05):
    model = YOLO(str(weights), task="detect")
    rows = [r for r in csv.DictReader(open("vision/splits/P-inat-v1.tsv"), delimiter="\t") if r["split"] == split]
    names = model.names
    preds, conf_m = [], Counter()
    for r in rows:
        img = cv2.imread(str(ROOT / r["file"]))
        if img is None:
            continue
        best = ("none", 0.0)
        for res in model.predict([letterbox(img, s) for s in SCALES], imgsz=imgsz, conf=conf, verbose=False, device="cpu"):
            for c, p in zip(res.boxes.cls.tolist(), res.boxes.conf.tolist()):
                if p > best[1]:
                    best = (names[int(c)], p)
        preds.append({"file": r["file"], "true": r["cls"], "pred": best[0], "conf": round(best[1], 3)})
        conf_m[(r["cls"], best[0])] += 1
    scored = [p for p in preds if p["true"] in SCORED]
    acc = sum(p["true"] == p["pred"] for p in scored) / max(1, len(scored))
    recall = {c: sum(p["pred"] == c for p in scored if p["true"] == c) / max(1, sum(p["true"] == c for p in scored)) for c in SCORED}
    detected = sum(p["pred"] != "none" for p in scored) / max(1, len(scored))
    labels = SCORED + ["shb", "none"]
    matrix = {t: {p: conf_m[(t, p)] for p in labels} for t in SCORED + ["shb", "varroa"]}
    return {"split": split, "n": len(scored), "accuracy": round(acc, 3), "any_detection": round(detected, 3),
            "recall": {k: round(v, 3) for k, v in recall.items()}, "confusion": matrix,
            "chance_accuracy": round(1 / len(SCORED), 3), "predictions": preds}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("weights", type=Path)
    ap.add_argument("--split", default="calib", choices=["calib", "test"])
    ap.add_argument("--imgsz", type=int, default=320)
    a = ap.parse_args()
    res = evaluate(a.weights, a.split, a.imgsz)
    out = a.weights.parent.parent / f"real_{a.split}.json"
    out.write_text(json.dumps(res, indent=2))
    print(json.dumps({k: v for k, v in res.items() if k != "predictions"}, indent=2))
