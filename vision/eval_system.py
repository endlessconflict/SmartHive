"""System-level check of the node pipeline (tier S): ncnn models, both stages, crops from the
full-resolution frame, exactly as visiond will run them. Scenes are generated fresh from the
validation sprite library, so no training sprite appears.

    python -m vision.eval_system <stage1_ncnn_dir> <stage2_ncnn_dir> --n 200
"""
import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from simulation.images import compose
from vision.pipeline import CLASSES, Detector


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / max(1e-9, (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def evaluate(s1, s2, n, seed, workers, thresholds=None, threads=3, verifier=None):
    lib = compose.build_library("val", seed + 10_000, workers)
    det = Detector(Path(s1), Path(s2), thresholds=thresholds, threads=threads, verifier=Path(verifier) if verifier else None)
    tp, fp, fn = Counter(), Counter(), Counter()
    v = Counter()  # varroa confusion on matched, sharp, walking bees
    scenes_with = Counter()
    scenes_hit = Counter()
    times = []
    for i in range(n):
        frame, labels, _ = compose.scene(100_000 + i, seed, lib)
        gt = [lb for lb in labels if lb["visible"] >= 0.3]
        rec = det(frame)
        times.append(rec["timing_ms"]["total"])
        used = set()
        for o in sorted(rec["objects"], key=lambda o: -o["conf"]):
            best, j = 0.0, None
            for k, g in enumerate(gt):
                if k not in used and g["cls"] == o["cls"]:
                    u = iou(o["box"], g["box"])
                    if u > best:
                        best, j = u, k
            if j is not None and best >= 0.5:
                used.add(j)
                tp[o["cls"]] += 1
                g = gt[j]
                if "varroa_p" in o and not g["flying"]:
                    truth = g["n_mites_visible"] > 0
                    pred = o["varroa_p"] >= det.th["varroa"]
                    v[(truth, pred)] += 1
            else:
                fp[o["cls"]] += 1
        for k, g in enumerate(gt):
            if k not in used:
                fn[g["cls"]] += 1
        for c in ("hornet", "shb"):
            if any(g["cls"] == c for g in gt):
                scenes_with[c] += 1
                scenes_hit[c] += any(o["cls"] == c for o in rec["objects"])
    per_class = {c: {"precision": round(tp[c] / max(1, tp[c] + fp[c]), 3), "recall": round(tp[c] / max(1, tp[c] + fn[c]), 3),
                     "tp": tp[c], "fp": fp[c], "fn": fn[c]} for c in CLASSES}
    vt = {"tp": v[(True, True)], "fp": v[(False, True)], "fn": v[(True, False)], "tn": v[(False, False)]}
    vt["precision"] = round(vt["tp"] / max(1, vt["tp"] + vt["fp"]), 3)
    vt["recall"] = round(vt["tp"] / max(1, vt["tp"] + vt["fn"]), 3)
    true_rate = (vt["tp"] + vt["fn"]) / max(1, sum(vt[k] for k in ("tp", "fp", "fn", "tn")))
    est_rate = (vt["tp"] + vt["fp"]) / max(1, sum(vt[k] for k in ("tp", "fp", "fn", "tn")))
    return {"tier": "S", "scenes": n, "detector_iou50": per_class,
            "scene_level_recall": {c: round(scenes_hit[c] / max(1, scenes_with[c]), 3) for c in scenes_with},
            "varroa_on_matched_bees": vt, "varroa_index_true_vs_estimated": [round(true_rate, 4), round(est_rate, 4)],
            "host_ms_per_frame_p50": round(float(np.median(times)), 1), "host_ms_per_frame_p95": round(float(np.percentile(times, 95)), 1)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage1")
    ap.add_argument("stage2")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument("--verifier", help="ncnn folder of the stage 1b species verifier")
    a = ap.parse_args()
    res = evaluate(a.stage1, a.stage2, a.n, a.seed, a.workers, threads=a.threads, verifier=a.verifier)
    out = Path(a.stage1).parent.parent / ("system_eval_verified.json" if a.verifier else "system_eval.json")
    out.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))
