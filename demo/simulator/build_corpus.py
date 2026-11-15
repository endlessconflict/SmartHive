"""Render a small corpus of synthetic hive-entrance frames and keep the ones the real detector agrees on.

Runs once, while the simulator image is built. The scenes come from the SmartHive-Vision generator (the
same one that trained the models, here with a different seed); the detector is the v0.5 ncnn pipeline the
Raspberry Pi runs. A frame goes into a folder only when the detector finds what the generator drew:

    calm/     bees, nothing the node would report
    hornet/   an Asian hornet the detector names (confidence >= 0.60)
    shb/      a small hive beetle the detector names
    varroa/   a bee with a mite the stage 2 classifier flags (varroa_p >= 0.60)

At run time the simulator picks a frame from the folder the scenario asks for and runs the detector on it
again, so every detection the dashboard shows was produced by the model, not written by hand.
"""

import argparse
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import cv2

from smarthive_vision.pipeline import Detector
from smarthive_vision.synth import compose

WANT = {"calm": 12, "hornet": 8, "shb": 8, "varroa": 8}


def bucket(truth: list[dict], found: dict) -> str | None:
    """Only frames the detector is sure about, so the run-time result does not depend on thread count or rounding."""
    objs = found["objects"]
    names = {o["cls"] for o in objs}
    top = {c: max((o["conf"] for o in objs if o["cls"] == c), default=0.0) for c in ("hornet", "shb")}
    p_max = max((o.get("varroa_p", 0.0) for o in objs if o["cls"] == "bee"), default=0.0)
    drew_hornet = any(t["cls"] == "hornet" and t["visible"] > 0.7 for t in truth)
    drew_shb = any(t["cls"] == "shb" and t["visible"] > 0.7 for t in truth)
    drew_mite = any(t["cls"] == "bee" and t["n_mites_visible"] > 0 for t in truth)
    clean = p_max < 0.45  # far below the 0.60 the node reports at
    if drew_hornet and top["hornet"] >= 0.6 and clean and "shb" not in names:
        return "hornet"
    if drew_shb and top["shb"] >= 0.6 and clean and "hornet" not in names:
        return "shb"
    if drew_mite and p_max >= 0.75 and not ({"hornet", "shb"} & names):
        return "varroa"
    if "bee" in names and clean and not ({"hornet", "shb"} & names) and not drew_hornet and not drew_shb:
        return "calm"
    return None


LIB: list = []
DET: Detector | None = None
ARGS: argparse.Namespace


def work(i: int) -> tuple[int, str | None, bytes | None]:
    global DET
    if DET is None:  # one detector per worker process, built after the fork
        cv2.setNumThreads(1)
        DET = Detector(ARGS.models / "stage1", ARGS.models / "stage2", verifier=ARGS.models / "stage1b", threads=1)
    frame, truth, _ = compose.scene(i, ARGS.seed, LIB)
    ok, jpg = cv2.imencode(".jpg", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88])
    # judge the frame as the node will see it: after JPEG, which moves the detector's scores
    seen = cv2.cvtColor(cv2.imdecode(jpg, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    kind = bucket(truth, DET(seen))
    return i, kind, (jpg.tobytes() if kind else None)


def main() -> None:
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--max-scenes", type=int, default=4000)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ARGS = ap.parse_args()

    LIB.extend(compose.build_library("val", ARGS.seed, ARGS.workers))
    have = {k: 0 for k in WANT}
    for k in WANT:
        (ARGS.out / k).mkdir(parents=True, exist_ok=True)
    with Pool(ARGS.workers) as pool:
        for i, kind, jpg in pool.imap_unordered(work, range(ARGS.max_scenes), chunksize=4):
            if kind is None or have[kind] >= WANT[kind]:
                continue
            have[kind] += 1
            (ARGS.out / kind / f"{have[kind]:02d}.jpg").write_bytes(jpg)
            print(f"scene {i}: {kind} ({have[kind]}/{WANT[kind]})", flush=True)
            if have == WANT:
                pool.terminate()
                return
    print("corpus incomplete:", have, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
