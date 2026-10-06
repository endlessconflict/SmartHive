"""Real photos with automatic labels (iteration v0.4): iNaturalist photos become detector training
images. The species comes from iNaturalist (research-grade identification), the box from YOLOE with
text prompts, so nobody draws a box. Pools must be disjoint from the frozen tier P split
(vision/inat.py download --exclude); photos from an observation that is in tier P are dropped as
well (another photo of the same insect at the same moment). Photographers do overlap: a few prolific
observers took most of the iNaturalist hornet photos, so an observer-disjoint split leaves 8 test
hornets. The results document states this.

    python -m vision.pseudolabel data/raw/inat_pool data/raw/inat_pool2 --out data/sim/R-inat-pseudo-v1
"""
import argparse
import csv
import json
import re
from pathlib import Path

import cv2
import torch
from ultralytics import YOLOE

from simulation.images.cutouts import PROMPTS, WEIGHTS

CLASSES = ["bee", "hornet", "shb", "other_insect"]
SPLIT = Path(__file__).parent / "splits" / "P-inat-v1.tsv"
PHOTOS = Path("data/raw/inat/photos.tsv")  # photo_id to observation_uuid, from vision/inat.py filter


def boxes(det, img, min_top=0.04, rel=0.5, min_other=0.3):
    """All insects in the photo: the most confident one, plus others nearly as confident.
    One observation is one species, so every box gets the photo's class. Boxes from 0.04 up were
    right on a visual check; at 0.02 they land on nests and empty frames."""
    r = det.predict(img, conf=0.08, agnostic_nms=True, verbose=False, device="cpu")[0]
    if not len(r.boxes) or float(r.boxes.conf.max()) < min_top:
        return []
    top = float(r.boxes.conf.max())
    return [b.tolist() for b, c in zip(r.boxes.xyxy, r.boxes.conf) if float(c) >= max(min_other, rel * top) or float(c) == top]


def yolo_line(cls, box, w, h):
    x0, y0, x1, y1 = box
    return f"{cls} {(x0 + x1) / 2 / w:.6f} {(y0 + y1) / 2 / h:.6f} {(x1 - x0) / w:.6f} {(y1 - y0) / h:.6f}"


def main(pools, out: Path, max_side=640, threads=4):
    torch.set_num_threads(threads)
    det = YOLOE(str(WEIGHTS / "yoloe-11s-seg.pt"))
    det.set_classes(PROMPTS, det.get_text_pe(PROMPTS))
    obs = {r["photo_id"]: r["observation_uuid"] for r in csv.DictReader(open(PHOTOS), delimiter="\t")}
    pid = lambda u: re.search(r"photos/(\d+)", u).group(1)
    banned = {obs[pid(r["source_url"])] for r in csv.DictReader(open(SPLIT), delimiter="\t")}
    (out / "images/train").mkdir(parents=True, exist_ok=True)
    (out / "labels/train").mkdir(parents=True, exist_ok=True)
    stats = {"photos": 0, "same_observation_as_P": 0, "no_box": 0, "kept": {}, "boxes": 0}
    credits = []
    for pool in pools:
        for r in csv.DictReader(open(pool / "manifest.tsv"), delimiter="\t"):
            stats["photos"] += 1
            if obs.get(pid(r["source_url"])) in banned:
                stats["same_observation_as_P"] += 1
                continue
            img = cv2.imread(str(pool / r["file"]))
            if img is None:
                continue
            s = max_side / max(img.shape[:2])
            if s < 1:
                img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            bs = boxes(det, img)
            if not bs:
                stats["no_box"] += 1
                continue
            h, w = img.shape[:2]
            name = f"{r['cls']}_{Path(r['file']).stem}"
            cv2.imwrite(str(out / "images/train" / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            (out / "labels/train" / f"{name}.txt").write_text("\n".join(yolo_line(CLASSES.index(r["cls"]), b, w, h) for b in bs) + "\n")
            stats["kept"][r["cls"]] = stats["kept"].get(r["cls"], 0) + 1
            stats["boxes"] += len(bs)
            credits.append({"file": f"{name}.jpg", **{k: r[k] for k in ("cls", "taxon_id", "license", "source_url", "observer_id")}})
    with open(out / "manifest.tsv", "w", newline="") as f:
        wr = csv.DictWriter(f, list(credits[0]), delimiter="\t", lineterminator="\n")
        wr.writeheader()
        wr.writerows(credits)
    (out / "stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pools", type=Path, nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()
    main(a.pools, a.out, threads=a.threads)
