"""Two-stage pest detection for the node. Only numpy, OpenCV and ncnn: no torch, fits the Pi 3B.

Stage 1 finds insects on a downscaled frame; stage 2 classifies each sharp bee, cropped from the
full-resolution frame, as varroa / clean. Frame results are aggregated into events (k of n).
Design: docs/03-vision/04-model-architecture.md, contract: "Output contract" section there.
"""
import math
import time
from collections import deque
from pathlib import Path

import cv2
import ncnn
import numpy as np

CLASSES = ["bee", "hornet", "shb", "other_insect"]
DEFAULT_THRESHOLDS = {"bee": 0.35, "hornet": 0.45, "shb": 0.5, "other_insect": 0.5, "varroa": 0.6}


class Net:
    """An ncnn model exported by vision/export.py (model.ncnn.param + model.ncnn.bin)."""

    def __init__(self, folder: Path, threads=3):
        self.net = ncnn.Net()
        self.net.opt.num_threads = threads
        self.net.opt.use_fp16_storage = True  # A53 has no fp16 math; fp16 storage still halves memory traffic
        self.net.opt.openmp_blocktime = 0  # do not spin; default 3 threads leaves a core to camd/uplinkd (all cores busy = 100x slower barriers)
        self.net.load_param(str(Path(folder) / "model.ncnn.param"))
        self.net.load_model(str(Path(folder) / "model.ncnn.bin"))

    def __call__(self, chw: np.ndarray) -> np.ndarray:
        # ncnn.Mat wraps the numpy buffer without copying: keep both alive until extract() has run,
        # or ncnn reads freed memory and returns noise (seen as near-zero precision in eval_system)
        x = np.ascontiguousarray(chw, dtype=np.float32)
        mat = ncnn.Mat(x)
        ex = self.net.create_extractor()
        ex.input("in0", mat)
        _, out = ex.extract("out0")
        return np.array(out)


def letterbox(img, size):
    h, w = img.shape[:2]
    k = size / max(h, w)
    nh, nw = round(h * k), round(w * k)
    out = np.full((size, size, 3), 114, np.uint8)
    top, left = (size - nh) // 2, (size - nw) // 2
    out[top:top + nh, left:left + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    return out, k, left, top


def crop(frame, box, pad=0.15, size=128):
    """Square crop around a box from the full-resolution frame (same as the training crops)."""
    x0, y0, x1, y1 = box
    c, s = ((x0 + x1) / 2, (y0 + y1) / 2), max(x1 - x0, y1 - y0) * (1 + 2 * pad)
    M = np.float32([[size / s, 0, size / 2 - c[0] * size / s], [0, size / s, size / 2 - c[1] * size / s]])
    return cv2.warpAffine(frame, M, (size, size), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_REFLECT)


VERIFIER_CLASSES = ["bee", "hornet", "other_insect"]  # ultralytics sorts class folders alphabetically


def decide(pred, v, vth=0.2, flip=0.6):
    """Stage 1b rule on verifier probabilities v (class -> p). A hornet stays a hornet only if the verifier
    gives it at least vth; a bee or other insect changes class only if the verifier is flip sure.
    Defaults chosen on tier P v2 calibration (v0.5): the most accurate pair with hornet recall >= 0.90
    and precision >= 0.70 (0.907 / 0.904)."""
    if pred == "hornet" and v["hornet"] < vth:
        return max(("bee", "other_insect"), key=v.get)
    if pred in ("bee", "other_insect"):
        best = max(VERIFIER_CLASSES, key=v.get)
        if best != pred and v[best] >= max(flip, vth if best == "hornet" else 0):
            return best
    return pred


class Detector:
    def __init__(self, stage1: Path, stage2: Path | None, imgsz=320, threads=3, thresholds=None, max_crops=16, min_sharpness=30.0,
                 verifier: Path | None = None, vth=0.2, flip=0.6):
        self.s1 = Net(stage1, threads)
        self.s2 = Net(stage2, threads) if stage2 else None
        self.v = Net(verifier, threads) if verifier else None
        self.vth, self.flip = vth, flip
        self.imgsz, self.max_crops, self.min_sharpness = imgsz, max_crops, min_sharpness
        self.th = dict(DEFAULT_THRESHOLDS, **(thresholds or {}))

    def stage1(self, frame):
        img, k, left, top = letterbox(frame, self.imgsz)
        out = self.s1(img.transpose(2, 0, 1) / 255.0)  # RGB, CHW, 0..1 as in training
        out = out.reshape(4 + len(CLASSES), -1).T  # rows: cx, cy, w, h, class scores (already sigmoid)
        cls = out[:, 4:].argmax(1)
        conf = out[np.arange(len(out)), 4 + cls]
        keep = conf >= min(self.th[c] for c in CLASSES)
        out, cls, conf = out[keep], cls[keep], conf[keep]
        keep = conf >= np.array([self.th[CLASSES[c]] for c in cls]) if len(cls) else np.zeros(0, bool)
        out, cls, conf = out[keep], cls[keep], conf[keep]
        boxes = np.stack([(out[:, 0] - out[:, 2] / 2 - left) / k, (out[:, 1] - out[:, 3] / 2 - top) / k,
                          (out[:, 0] + out[:, 2] / 2 - left) / k, (out[:, 1] + out[:, 3] / 2 - top) / k], 1) if len(out) else np.zeros((0, 4))
        idx = cv2.dnn.NMSBoxesBatched([[b[0], b[1], b[2] - b[0], b[3] - b[1]] for b in boxes.tolist()], conf.tolist(), cls.tolist(), 0.0, 0.5) if len(boxes) else []
        H, W = frame.shape[:2]
        return [{"cls": CLASSES[int(cls[i])], "conf": round(float(conf[i]), 3),
                 "box": [int(max(0, boxes[i][0])), int(max(0, boxes[i][1])), int(min(W, boxes[i][2])), int(min(H, boxes[i][3]))]}
                for i in np.array(idx).reshape(-1)]

    def __call__(self, frame_rgb):
        """frame_rgb: full-resolution RGB uint8. Returns the per-frame record of the output contract."""
        t0 = time.perf_counter()
        objs = self.stage1(frame_rgb)
        if self.v:  # stage 1b: only hornet and other-insect candidates, rare at an entrance
            for o in objs:
                if o["cls"] in ("hornet", "other_insect"):
                    p = self.v(crop(frame_rgb, o["box"], size=160).transpose(2, 0, 1) / 255.0).reshape(-1)
                    v = dict(zip(VERIFIER_CLASSES, p.tolist()))
                    o["detector_cls"], o["cls"] = o["cls"], decide(o["cls"], v, self.vth, self.flip)
                    o["verifier_p"] = round(v[o["cls"]], 3)
        t1 = time.perf_counter()
        if self.s2:
            bees = sorted((o for o in objs if o["cls"] == "bee"), key=lambda o: -o["conf"])[: self.max_crops]
            for o in bees:
                c = crop(frame_rgb, o["box"])
                sharp = cv2.Laplacian(cv2.cvtColor(c, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var() >= self.min_sharpness
                o["sharp"] = bool(sharp)
                if sharp:  # flying or blurred bees cannot show a mite: skip, do not guess
                    probs = self.s2(c.transpose(2, 0, 1) / 255.0).reshape(-1)
                    o["varroa_p"] = round(float(probs[self.s2_varroa_index]), 3)
        t2 = time.perf_counter()
        return {"objects": objs, "timing_ms": {"stage1": round((t1 - t0) * 1e3, 1), "stage2": round((t2 - t1) * 1e3, 1),
                                               "total": round((t2 - t0) * 1e3, 1)}}

    s2_varroa_index = 1  # ultralytics sorts class folders: ["clean", "varroa"]


class MotionGate:
    """Cheap check on a low-res stream: run the detector only when something moved."""

    def __init__(self, threshold=0.002):
        self.bg = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=25, detectShadows=False)
        self.threshold = threshold

    def __call__(self, small_gray) -> bool:
        fg = self.bg.apply(small_gray)
        return (fg > 0).mean() > self.threshold


def wilson(pos, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 1.0)
    p = pos / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0.0, c - h), min(1.0, c + h))


class Aggregator:
    """k-of-n rule for threats and a rolling Varroa index with a 95 % Wilson interval."""

    def __init__(self, rules=None, varroa_th=0.6):
        self.rules = rules or {"hornet": (3, 10), "shb": (2, 10)}
        self.windows = {c: deque(maxlen=n) for c, (k, n) in self.rules.items()}
        self.varroa_th = varroa_th
        self.bees = self.positive = 0
        self.active = set()

    def update(self, record):
        events = []
        for c, (k, n) in self.rules.items():
            self.windows[c].append(any(o["cls"] == c for o in record["objects"]))
            hit = sum(self.windows[c]) >= k
            if hit and c not in self.active:
                events.append({"type": "threat_detected", "cls": c, "frames_positive": sum(self.windows[c]), "frames_window": n})
            (self.active.add if hit else self.active.discard)(c)
        for o in record["objects"]:
            if "varroa_p" in o:
                self.bees += 1
                self.positive += o["varroa_p"] >= self.varroa_th
        return events

    def varroa_index(self):
        p, lo, hi = wilson(self.positive, self.bees)
        return {"bees_classified": self.bees, "positive": self.positive, "index": round(p, 4), "ci95": [round(lo, 4), round(hi, 4)]}


if __name__ == "__main__":
    agg = Aggregator()
    assert agg.update({"objects": [{"cls": "hornet"}]}) == [] and agg.update({"objects": [{"cls": "hornet"}]}) == []
    assert agg.update({"objects": [{"cls": "hornet"}]})[0]["cls"] == "hornet"  # third sighting in 10 frames
    assert agg.update({"objects": [{"cls": "hornet"}]}) == []  # same episode, no duplicate event
    assert decide("hornet", {"bee": 0.1, "hornet": 0.15, "other_insect": 0.75}) == "other_insect"
    assert decide("hornet", {"bee": 0.1, "hornet": 0.3, "other_insect": 0.6}) == "hornet"
    assert decide("other_insect", {"bee": 0.05, "hornet": 0.65, "other_insect": 0.3}) == "hornet"
    assert decide("other_insect", {"bee": 0.2, "hornet": 0.5, "other_insect": 0.3}) == "other_insect"
    p, lo, hi = wilson(3, 100)
    assert abs(p - 0.03) < 1e-9 and 0.005 < lo < 0.03 < hi < 0.09
    release = Path(__file__).parent.parent / "models/v0.2/stage1"
    if release.exists():  # same input, same output: guards the ncnn.Mat lifetime bug
        net, x = Net(release), np.random.default_rng(0).random((3, 320, 320))
        ref = net(x)
        for _ in range(20):
            junk = [np.ones(x.size) for _ in range(3)]  # reuse freed memory if a buffer is released too early
            assert np.allclose(net(x), ref, atol=1e-3)
    print("ok")
