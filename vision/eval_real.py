"""Tier P check: does a detector trained only on procedural insects recognise real ones?

iNaturalist photos have no boxes and no fixed scale, so this is an image-level test: each photo
is letterboxed at three scales (insect large, medium, entrance-camera small), the detector runs on
all three, and the most confident detection names the photo. Classes without enough photos
(shb: 2, varroa: 10) are reported but not scored.

    python -m vision.eval_real runs/stage1/<run>/weights/best.pt --split calib
    python -m vision.eval_real <best.pt> --tier P2 --split calib --verifier <verifier best.pt> --vth 0.5

Tier P2 (vision/splits/P-inat-v2.tsv) shares no photographer with any training pool and leans on the
insects that get confused with hornets and bees; its rows carry a group, reported separately.
With --verifier, the top detection is cut from the original photo and re-classified (stage 1b).
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

TIERS = {"P1": (Path("vision/splits/P-inat-v1.tsv"), Path("data/raw/inat")),
         "P2": (Path("vision/splits/P-inat-v2.tsv"), Path("data/raw/inat26_photos"))}
SCORED = ["bee", "hornet", "other_insect"]
SCALES = (640, 320, 160)


def letterbox(img, side, canvas=640):
    """Returns the canvas and (k, x, y): a canvas point p maps back to the photo as (p - (x, y)) / k."""
    h, w = img.shape[:2]
    k = side / max(h, w)
    small = cv2.resize(img, (max(1, int(w * k)), max(1, int(h * k))), interpolation=cv2.INTER_AREA)
    out = np.full((canvas, canvas, 3), 114, np.uint8)
    y, x = (canvas - small.shape[0]) // 2, (canvas - small.shape[1]) // 2
    out[y:y + small.shape[0], x:x + small.shape[1]] = small
    return out, (k, x, y)


def verify(verifier, img, box, vth, pred):
    """Stage 1b on a crop of the original photo, with the node's rule (vision.pipeline.decide)."""
    from vision.pipeline import crop, decide
    probs = verifier.predict(crop(img, box, size=160), imgsz=160, verbose=False, device="cpu")[0].probs.data.tolist()
    return decide(pred, dict(zip(verifier.names.values(), probs)), vth)


def evaluate(weights, split, imgsz, conf=0.05, tier="P1", verifier=None, vth=0.5):
    model = YOLO(str(weights), task="detect")
    split_file, root = TIERS[tier]
    rows = [r for r in csv.DictReader(open(split_file), delimiter="\t") if r["split"] == split]
    names = model.names
    ver = YOLO(str(verifier), task="classify") if verifier else None
    preds, conf_m = [], Counter()
    for r in rows:
        img = cv2.imread(str(root / r["file"]))
        if img is None:
            continue
        best = ("none", 0.0, None)
        boards = [letterbox(img, s) for s in SCALES]
        for (_, (k, x, y)), res in zip(boards, model.predict([b for b, _ in boards], imgsz=imgsz, conf=conf, verbose=False, device="cpu")):
            for c, p, b in zip(res.boxes.cls.tolist(), res.boxes.conf.tolist(), res.boxes.xyxy.tolist()):
                if p > best[1]:
                    best = (names[int(c)], p, [(b[0] - x) / k, (b[1] - y) / k, (b[2] - x) / k, (b[3] - y) / k])
        pred = verify(ver, img, best[2], vth, best[0]) if ver and best[2] and best[0] != "shb" else best[0]
        preds.append({"file": r["file"], "true": r["cls"], "group": r.get("group", ""), "detector": best[0], "pred": pred, "conf": round(best[1], 3)})
        conf_m[(r["cls"], pred)] += 1
    scored = [p for p in preds if p["true"] in SCORED]
    acc = sum(p["true"] == p["pred"] for p in scored) / max(1, len(scored))
    recall = {c: sum(p["pred"] == c for p in scored if p["true"] == c) / max(1, sum(p["true"] == c for p in scored)) for c in SCORED}
    detected = sum(p["pred"] != "none" for p in scored) / max(1, len(scored))
    labels = SCORED + ["shb", "none"]
    matrix = {t: {p: conf_m[(t, p)] for p in labels} for t in SCORED + ["shb", "varroa"]}
    precision = {c: sum(p["true"] == c for p in scored if p["pred"] == c) / max(1, sum(p["pred"] == c for p in preds)) for c in SCORED}
    groups = Counter((p["group"], p["pred"]) for p in scored if p["true"] == "other_insect")
    by_group = {g: {"n": sum(v for (gg, _), v in groups.items() if gg == g), "called_hornet": groups[(g, "hornet")]}
                for g in sorted({g for g, _ in groups})}
    return {"tier": tier, "split": split, "verifier": str(verifier) if verifier else None, "n": len(scored), "accuracy": round(acc, 3),
            "any_detection": round(detected, 3), "recall": {k: round(v, 3) for k, v in recall.items()},
            "precision": {k: round(v, 3) for k, v in precision.items()}, "other_by_group": by_group, "confusion": matrix,
            "chance_accuracy": round(1 / len(SCORED), 3), "predictions": preds}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("weights", type=Path)
    ap.add_argument("--split", default="calib", choices=["calib", "test"])
    ap.add_argument("--imgsz", type=int, default=320)
    ap.add_argument("--tier", default="P1", choices=list(TIERS))
    ap.add_argument("--verifier", type=Path)
    ap.add_argument("--vth", type=float, default=0.5)
    a = ap.parse_args()
    res = evaluate(a.weights, a.split, a.imgsz, tier=a.tier, verifier=a.verifier, vth=a.vth)
    suffix = ("" if a.tier == "P1" else "_p2") + ("_verified" if a.verifier else "")
    out = a.weights.parent.parent / f"real_{a.split}{suffix}.json"
    out.write_text(json.dumps(res, indent=2))
    print(json.dumps({k: v for k, v in res.items() if k != "predictions"}, indent=2))
