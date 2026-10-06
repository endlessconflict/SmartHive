"""Real-photo insect cutouts (RGBA) for the hybrid sprite library (ADR-0009, option kept open there).

Source: an iNaturalist asset pool that is disjoint from the frozen tier P split (vision/inat.py
download --exclude). YOLOE with text prompts finds the insect (the species label comes from
iNaturalist, not from YOLOE); SAM 2.1 tiny turns the box into a mask; shape checks drop bad masks.
Photos without a confident insect box are skipped: a wrong cutout labeled "bee" is worse than none.

    python -m simulation.images.cutouts data/raw/inat_pool data/assets/cutouts-v1
"""
import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import SAM, YOLOE

WEIGHTS = Path("data/weights")


PROMPTS = ["insect", "honeybee", "bee", "hornet", "wasp", "fly", "ant", "beetle"]


def best_box(det, img):
    r = det.predict(img, conf=0.08, verbose=False, device="cpu")[0]
    if not len(r.boxes):
        return 0.0, None
    i = int(r.boxes.conf.argmax())
    return float(r.boxes.conf[i]), r.boxes.xyxy[i].tolist()


def good(mask):
    """Keep compact, mid-sized masks that do not run along the photo border."""
    h, w = mask.shape
    area = mask.mean()
    if not 0.005 < area < 0.45:
        return False
    border = np.concatenate([mask[0], mask[-1], mask[:, 0], mask[:, -1]]).mean()
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
    main = stats[1:, cv2.CC_STAT_AREA].max() / max(1, mask.sum()) if n > 1 else 0
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hull = cv2.contourArea(cv2.convexHull(max(cnts, key=cv2.contourArea))) if cnts else 1
    solidity = mask.sum() / max(1, hull)
    return border < 0.05 and main > 0.9 and solidity > 0.55


def main(pool: Path, out: Path, limit: int | None, min_conf=0.12, threads=2):
    torch.set_num_threads(threads)
    det, sam = YOLOE(str(WEIGHTS / "yoloe-11s-seg.pt")), SAM(str(WEIGHTS / "sam2.1_t.pt"))
    det.set_classes(PROMPTS, det.get_text_pe(PROMPTS))
    rows = list(csv.DictReader(open(pool / "manifest.tsv"), delimiter="\t"))[:limit]
    out.mkdir(parents=True, exist_ok=True)
    kept = []
    for r in rows:
        img = cv2.imread(str(pool / r["file"]))
        if img is None:
            continue
        conf, box = best_box(det, img)
        if conf < min_conf:
            continue
        h, w = img.shape[:2]
        res = sam.predict(img, bboxes=[box], verbose=False, device="cpu")[0]
        if res.masks is None or len(res.masks.data) == 0:
            continue
        mask = res.masks.data[0].cpu().numpy() > 0.5
        if not good(mask):
            continue
        ys, xs = np.nonzero(mask)
        pad = 4
        y0, y1, x0, x1 = max(0, ys.min() - pad), min(h, ys.max() + pad), max(0, xs.min() - pad), min(w, xs.max() + pad)
        alpha = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 0.8)[y0:y1, x0:x1]
        rgba = np.dstack([img[y0:y1, x0:x1], (alpha * 255).astype(np.uint8)])
        name = f"{r['cls']}_{Path(r['file']).stem}.png"
        cv2.imwrite(str(out / name), rgba)
        kept.append({"file": name, "cls": r["cls"], "taxon_id": r["taxon_id"], "license": r["license"],
                     "source_url": r["source_url"], "observer_id": r["observer_id"], "box_conf": round(conf, 3)})
    with open(out / "manifest.tsv", "w", newline="") as f:
        wr = csv.DictWriter(f, list(kept[0]), delimiter="\t", lineterminator="\n")
        wr.writeheader()
        wr.writerows(kept)
    print(json.dumps({"photos": len(rows), "kept": len(kept),
                      "per_class": {c: sum(k["cls"] == c for k in kept) for c in sorted({k["cls"] for k in kept})}}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pool", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--threads", type=int, default=2)
    a = ap.parse_args()
    main(a.pool, a.out, a.limit, threads=a.threads)
