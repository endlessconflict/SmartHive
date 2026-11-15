"""Build corpus/: demo frames made of real photographs of the BeeAlarmed BeeDataset, kept only when the
detector agrees with the dataset's own label.

    python build_corpus.py --dataset <BeeDataset folder with data.json and images_300/> --out corpus

BeeDataset (https://github.com/BeeAlarmed/BeeDataset, GPL-3.0, Fabian Hickert) is the dataset the detector was
trained on, so these are in-distribution photographs, not a test of generalization: the demo shows the
pipeline, not the model's field accuracy. Each frame is three single-bee photographs side by side, 960 x 640:

    calm/     three bees the dataset labels as healthy
    hornet/   a wasp (the dataset's label `wasps`) between two bees; the detector's class is `wasp`
    varroa/   a bee the dataset labels `varroa` between two healthy bees; the mite is a separate box

A frame is kept only when the detector finds what the label says, with margin: wasp >= 0.70, varroa >= 0.70,
and for `calm` nothing above 0.45 that is not a bee. The images land in corpus/ with a MANIFEST.tsv that lists
the dataset file behind every tile, so each one can be traced to its source.
"""

import argparse
import json
import random
from pathlib import Path

import cv2
import numpy as np

from detector import PestDetector

WANT = {"calm": 12, "hornet": 10, "varroa": 10}
H = 640


def tile(path: Path) -> np.ndarray:
    im = cv2.imread(str(path))
    return cv2.resize(im, (round(im.shape[1] * H / im.shape[0]), H), interpolation=cv2.INTER_CUBIC)


def verdict(kind: str, found: list[dict]) -> bool:
    top = {c: max((o["conf"] for o in found if o["cls"] == c), default=0.0) for c in ("bee", "varroa", "wasp")}
    if kind == "calm":
        return top["bee"] >= 0.6 and top["varroa"] < 0.45 and top["wasp"] < 0.45
    if kind == "hornet":
        return top["wasp"] >= 0.70 and top["varroa"] < 0.45
    return top["varroa"] >= 0.70 and top["wasp"] < 0.45


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", type=Path, default=Path(__file__).parent / "model" / "yolo11n_v2.onnx")
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()

    labels = json.loads((args.dataset / "data.json").read_text())
    pools = {
        "calm": [f for f, v in labels.items() if not v["varroa"] and not v["wasps"]],
        "hornet": [f for f, v in labels.items() if v["wasps"]],
        "varroa": [f for f, v in labels.items() if v["varroa"] and not v["wasps"]],
    }
    rng = random.Random(args.seed)
    for p in pools.values():
        rng.shuffle(p)
    det = PestDetector(args.model, threads=4)
    manifest = ["frame\ttiles"]
    for kind, want in WANT.items():
        (args.out / kind).mkdir(parents=True, exist_ok=True)
        got, tries = 0, 0
        while got < want and tries < 600:
            tries += 1
            lead = pools[kind].pop()
            fillers = rng.sample(pools["calm"], 2)
            tiles = [lead, *fillers] if kind != "calm" else [lead, *fillers]
            order = [0, 1, 2]
            rng.shuffle(order)
            files = [tiles[i] for i in order]
            frame = np.hstack([tile(args.dataset / "images_300" / f) for f in files])
            if verdict(kind, det(frame)):
                got += 1
                name = f"{kind}/{got:02d}.jpg"
                cv2.imwrite(str(args.out / name), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                manifest.append(f"{name}\t{' '.join(files)}")
        print(kind, got, "kept of", tries, "tried")
        assert got == want, f"only {got} {kind} frames agree with their labels"
    (args.out / "MANIFEST.tsv").write_text("\n".join(manifest) + "\n")


if __name__ == "__main__":
    main()
