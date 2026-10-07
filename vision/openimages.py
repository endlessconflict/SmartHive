"""Real photos with human-drawn bee boxes from Open Images V7 (images CC BY 2.0 via Flickr, boxes CC BY 4.0).

Keeps images whose bees are boxed one by one: an image with a group box ("IsGroupOf", a swarm drawn as one
box) or a drawing ("IsDepiction") is dropped, because its other bees would be unlabeled. Open Images'
"Bee" means any bee, bumblebees included, so the class is checked later by the species verifier
(vision/verifier.py) before these boxes are used as "bee".

    python -m vision.openimages data/raw/openimages --out data/raw/oi-bees
"""
import argparse
import csv
import urllib.request
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

BEE = "/m/01h3n"
META = {"train": "https://storage.googleapis.com/openimages/2018_04/train/train-images-boxable-with-rotation.csv",
        "validation": "https://storage.googleapis.com/openimages/2018_04/validation/validation-images-with-rotation.csv",
        "test": "https://storage.googleapis.com/openimages/2018_04/test/test-images-with-rotation.csv"}
IMAGES = "https://open-images-dataset.s3.amazonaws.com/{split}/{image_id}.jpg"


def select(box_dir: Path):
    """image (split, id) -> list of bee boxes (x0, y0, x1, y1, normalized); unusable images removed."""
    boxes, bad = defaultdict(list), set()
    for f in sorted(box_dir.glob("*-insect-bbox.csv")):
        split = f.name.split("-")[0]
        for r in csv.DictReader(open(f)):
            if r["LabelName"] != BEE:
                continue
            key = (split, r["ImageID"])
            if r["IsGroupOf"] == "1" or r["IsDepiction"] == "1":
                bad.add(key)
            boxes[key].append(tuple(float(r[k]) for k in ("XMin", "YMin", "XMax", "YMax")))
    return {k: v for k, v in boxes.items() if k not in bad}


def credits(keys):
    """Author, license and source URL of each kept image, streamed from the per-split metadata files."""
    want = defaultdict(set)
    for split, i in keys:
        want[split].add(i)
    out = {}
    for split, ids in want.items():
        with urllib.request.urlopen(META[split]) as resp:
            header = None
            for line in resp:
                r = next(csv.reader([line.decode("utf-8", "replace")]))
                if header is None:
                    header = {k: n for n, k in enumerate(r)}
                elif r[0] in ids:
                    out[(split, r[0])] = {k: r[header[k]] for k in ("OriginalURL", "OriginalLandingURL", "License", "Author", "Rotation")}
    return out


def main(box_dir: Path, out: Path, max_side=640):
    sel = select(box_dir)
    meta = credits(sel)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    rows = []
    for (split, i), bs in sorted(sel.items()):
        m = meta.get((split, i))
        if m is None or float(m["Rotation"] or 0):  # rotated images: boxes refer to the displayed orientation; skip
            continue
        dst = out / "images" / f"oi_{i}.jpg"
        if not dst.exists():
            try:
                data = urllib.request.urlopen(IMAGES.format(split=split, image_id=i), timeout=60).read()
            except OSError as e:
                print("skip", i, e)
                continue
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            s = max_side / max(img.shape[:2])
            if s < 1:
                img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(dst), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        (out / "labels" / f"oi_{i}.txt").write_text(
            "".join(f"0 {(x0 + x1) / 2:.6f} {(y0 + y1) / 2:.6f} {x1 - x0:.6f} {y1 - y0:.6f}\n" for x0, y0, x1, y1 in bs))
        rows.append({"file": dst.name, "split": split, "bee_boxes": len(bs), "license": m["License"],
                     "author": m["Author"], "source_url": m["OriginalLandingURL"] or m["OriginalURL"]})
    with open(out / "manifest.tsv", "w", newline="") as f:
        w = csv.DictWriter(f, list(rows[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(len(sel), "usable images,", len(rows), "downloaded,", sum(r["bee_boxes"] for r in rows), "bee boxes")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("boxes", type=Path, help="folder with <split>-insect-bbox.csv files")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    main(a.boxes, a.out)
