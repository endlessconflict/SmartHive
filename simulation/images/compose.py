"""Synthetic entrance images with exact labels. Design: docs/03-vision/03-synthetic-image-pipeline.md

    python -m simulation.images.compose --out data/sim/S-images-entrance-v0.1-s1 --n 4000 --seed 1

Two steps, both deterministic from the seed:
1. sprite library: procedural insects (render.py) at a reference scale; train and val use
   different library seeds, so validation never sees a training sprite.
2. scenes: procedural landing board + entrance, insects placed by simple behavior rules,
   shadows, lighting, camera blur/noise/JPEG. Labels come from the visible (occlusion-aware) masks.

Outputs (Ultralytics layouts):
  stage1/images/{train,val}/*.jpg  stage1/labels/...  stage1/data.yaml   640x480, classes below
  stage2/{train,val}/{varroa,clean}/*.jpg                                 128x128 bee crops
  objects.parquet, DATASET_CARD.md
"""
import argparse
import csv
import hashlib
import json
import subprocess
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from simulation.images import render

VERSION = "0.3.0"
CLASSES = ["bee", "hornet", "shb", "other_insect"]
FULL = (1640, 1232)  # Raspberry Pi Camera v2 2x2-binned mode; the node analyzes frames this size
STAGE1 = (640, 480)
REF_PX_MM = 12.0  # library scale; scenes only downscale from it
LIB_COUNTS = {"train": {"bee": 1600, "hornet": 300, "shb": 250, "other_insect": 500},
              "val": {"bee": 300, "hornet": 60, "shb": 50, "other_insect": 100}}


# ---- sprite library -------------------------------------------------------------------------

def _sprite(args):
    cv2.setNumThreads(1)  # one process per core; nested threads only oversubscribe
    seed, cls = args
    rng = np.random.default_rng(seed)
    sp = render.sample_species(rng, "other" if cls == "other_insect" else cls)
    flying = rng.random() < {"bee": 0.15, "hornet": 0.5, "shb": 0.0, "other_insect": 0.3}[cls]
    mites = int(rng.choice([0, 1, 2, 3], p=[0.55, 0.28, 0.13, 0.04])) if cls == "bee" and not flying else 0
    pollen = cls == "bee" and rng.random() < 0.3
    rgba, info = render.render(rng, sp, REF_PX_MM, flying=flying, mites=mites, pollen=pollen)
    return dict(cls=cls, kind=sp["kind"], flying=flying, mites=info["mites_px"], pollen=pollen,
                length_mm=sp["L"], rgba=(rgba * 255).astype(np.uint8))


def build_library(split, seed, workers):
    jobs = [(int(seed) * 1_000_003 + i * 7919 + k, cls) for k, (cls, n) in enumerate(LIB_COUNTS[split].items())
            for i in range(n)]
    with Pool(workers) as p:
        return p.map(_sprite, jobs, chunksize=16)


BODY_MM = {"bee": (12, 15), "hornet": (20, 30), "other_insect": (6, 16)}


def load_cutouts(folder: Path, split: str):
    """Real-photo cutouts (simulation/images/cutouts.py). One file in five goes to val, by name hash,
    so train and val never share a real insect. Bees get procedural mites painted on 45 % of the time,
    otherwise stage 2 could learn 'real-looking bee = clean'."""
    out = []
    for r in csv.DictReader(open(folder / "manifest.tsv"), delimiter="\t"):
        h = int(hashlib.md5(r["file"].encode()).hexdigest(), 16)
        if (h % 5 == 0) != (split == "val"):
            continue
        rng = np.random.default_rng(h % 2**32)
        rgba = cv2.cvtColor(cv2.imread(str(folder / r["file"]), cv2.IMREAD_UNCHANGED), cv2.COLOR_BGRA2RGBA)
        length = rng.uniform(*BODY_MM[r["cls"]])
        k = length * REF_PX_MM * 1.2 / max(rgba.shape[:2])  # long side covers body plus legs/wings
        rgba = cv2.resize(rgba, (max(3, int(rgba.shape[1] * k)), max(3, int(rgba.shape[0] * k))), interpolation=cv2.INTER_AREA)
        n = int(np.hypot(*rgba.shape[:2])) + 2  # square canvas so scene() can rotate it like a sprite
        sq = np.zeros((n, n, 4), np.uint8)
        y0, x0 = (n - rgba.shape[0]) // 2, (n - rgba.shape[1]) // 2
        sq[y0:y0 + rgba.shape[0], x0:x0 + rgba.shape[1]] = rgba
        mites = []
        if r["cls"] == "bee" and rng.random() < 0.45:
            inner = cv2.erode((sq[..., 3] > 230).astype(np.uint8), np.ones((9, 9), np.uint8))
            ys, xs = np.nonzero(inner)
            for _ in range(int(rng.choice([1, 2], p=[0.75, 0.25])) if len(xs) else 0):
                j = rng.integers(len(xs))
                cv = render.Canvas(int(2.2 * REF_PX_MM) | 1)
                render.varroa(cv, rng, 0, 0, REF_PX_MM, rng.uniform(0, 2 * np.pi))
                m = cv.n // 2
                ya, xa = ys[j] - m, xs[j] - m
                if ya < 0 or xa < 0 or ya + cv.n > n or xa + cv.n > n:
                    continue
                a = cv.a[..., None]
                patch = sq[ya:ya + cv.n, xa:xa + cv.n, :3].astype(np.float32) / 255
                sq[ya:ya + cv.n, xa:xa + cv.n, :3] = ((cv.rgb * a + patch * (1 - a)) * 255).astype(np.uint8)
                mites.append((float(xs[j]), float(ys[j])))
        out.append(dict(cls=r["cls"], kind="real", flying=False, mites=mites, pollen=False, length_mm=length, rgba=sq))
    return out


# ---- background -----------------------------------------------------------------------------

def board(rng, W, H):
    """Landing board: wood or paint, dirt, propolis, debris, entrance slot. Returns rgb and entrance info."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r0 = rng.random()
    if r0 < DR_FRAC:  # domain randomization: an arbitrary multi-scale texture instead of a board
        img = sum(render._noise(rng, H, W, sc)[..., None] * rng.uniform(-0.5, 0.5, 3) for sc in (300, 60, 12))
        img = np.clip(img + rng.uniform(0.2, 0.7, 3), 0, 1).astype(np.float32)
    elif r0 < DR_FRAC + (1 - DR_FRAC) * 0.55:  # wood grain along a random plank direction
        base = render._hsv(rng.uniform(20, 38), rng.uniform(0.25, 0.6), rng.uniform(0.35, 0.75))
        ang = rng.uniform(-0.2, 0.2) + (np.pi / 2 if rng.random() < 0.3 else 0)
        u = xx * np.cos(ang) + yy * np.sin(ang)
        v = -xx * np.sin(ang) + yy * np.cos(ang)
        warp = render._noise(rng, H, W, rng.uniform(40, 120)) * rng.uniform(4, 15) + render._noise(rng, H, W, 6) * 1.5
        grain = np.clip(np.sin((v + warp) / rng.uniform(1.2, 3.5)) * 0.5 + 0.5 + 0.3 * render._noise(rng, H, W, 3), 0, 1) ** 2
        img = base * (0.8 + 0.25 * grain[..., None]) * (1 + 0.15 * render._noise(rng, H, W, 300)[..., None])
        for s in rng.uniform(0, 1, int(rng.integers(0, 3))) * H:  # plank seams
            img[np.abs(v - s) < rng.uniform(1, 3)] *= 0.4
    else:
        paints = [(40, 0.08, 0.92), (45, 0.2, 0.9), (200, 0.25, 0.8), (110, 0.25, 0.7), (50, 0.6, 0.85), (0, 0, 0.6)]
        h, s, v = paints[rng.integers(len(paints))]
        img = np.broadcast_to(render._hsv(h, s, v), (H, W, 3)).copy()
        img *= (1 + 0.06 * render._noise(rng, H, W, 8)[..., None])
        worn = render._noise(rng, H, W, rng.uniform(15, 40)) > rng.uniform(0.75, 0.95)  # small chips show wood
        img[worn] = render._hsv(28, 0.45, 0.5) * (0.8 + 0.4 * rng.random()) * (1 + 0.2 * render._noise(rng, H, W, 4))[worn][:, None]
    # dirt, propolis stains and bee droppings
    stain = cv2.GaussianBlur(np.clip(render._noise(rng, H, W, rng.uniform(80, 300)) * 1.5 - 0.7, 0, 1), (0, 0), 8)[..., None]
    img = img * (1 - rng.uniform(0.1, 0.35) * stain) + render._hsv(25, 0.7, 0.25) * 0.2 * stain
    for _ in range(int(rng.integers(50, 400))):
        c = (int(rng.integers(W)), int(rng.integers(H)))
        col = rng.choice([render._hsv(30, 0.6, 0.35), render._hsv(45, 0.7, 0.6), render._hsv(0, 0, 0.15)])
        cv2.circle(img, c, int(rng.integers(1, 4)), col.tolist(), -1, cv2.LINE_AA)
    debris = []
    for _ in range(int(rng.integers(0, 12))):  # pollen pellets, wax flakes, twigs: hard negatives
        c = (int(rng.integers(W)), int(rng.integers(H)))
        kind = rng.choice(["pollen", "wax", "twig"])
        if kind == "pollen":
            cv2.ellipse(img, c, (int(rng.integers(4, 9)), int(rng.integers(3, 7))), rng.uniform(0, 180), 0, 360,
                        render._hsv(rng.choice([0, 15, 30, 45, 55, 280]), rng.uniform(0.6, 1), rng.uniform(0.5, 0.95)).tolist(), -1, cv2.LINE_AA)
        elif kind == "wax":
            pts = (np.array(c) + rng.normal(0, 6, (6, 2))).astype(np.int32)
            cv2.fillPoly(img, [pts], render._hsv(45, 0.2, 0.9).tolist(), cv2.LINE_AA)
        else:
            e = (np.array(c) + rng.normal(0, 40, 2)).astype(int)
            cv2.line(img, c, tuple(int(x) for x in e), render._hsv(30, 0.5, 0.3).tolist(), int(rng.integers(2, 5)), cv2.LINE_AA)
        debris.append(kind)
    # entrance: dark slot along the top edge (or the left edge), with the hive interior in shadow
    side = "top" if rng.random() < 0.75 else "left"
    depth = int(rng.uniform(0.05, 0.16) * (H if side == "top" else W))
    span = (int(rng.uniform(0, 0.25) * W), int(rng.uniform(0.75, 1.0) * W)) if side == "top" else (int(rng.uniform(0, 0.2) * H), int(rng.uniform(0.8, 1) * H))
    dark = render._hsv(25, 0.5, rng.uniform(0.03, 0.1))
    if side == "top":
        img[:depth, span[0]:span[1]] = dark * (1 + 0.5 * yy[:depth, span[0]:span[1], None] / depth)
    else:
        img[span[0]:span[1], :depth] = dark * (1 + 0.5 * xx[span[0]:span[1], :depth, None] / depth)
    return np.clip(img, 0, 1).astype(np.float32), dict(side=side, depth=depth, span=span, debris=len(debris))


# ---- scene ----------------------------------------------------------------------------------

def place(rng, ent, W, H, flying):
    """Position and heading: walkers cluster in front of the entrance and face to/from it."""
    if flying:
        return rng.uniform(0, W), rng.uniform(0, H), rng.uniform(0, 2 * np.pi)
    d = rng.exponential(0.22) * (H if ent["side"] == "top" else W) + ent["depth"]
    a = rng.uniform(*ent["span"])
    x, y = (a, d) if ent["side"] == "top" else (d, a)
    to_entrance = -np.pi / 2 if ent["side"] == "top" else np.pi  # image coords, angle measured CCW
    r = rng.random()
    heading = to_entrance if r < 0.5 else (to_entrance + np.pi if r < 0.8 else rng.uniform(0, 2 * np.pi))
    return float(np.clip(x, 0, W - 1)), float(np.clip(y, 0, H - 1)), heading + rng.normal(0, 0.6)


def scene(i, seed, lib):
    rng = np.random.default_rng([seed, i])
    W, H = FULL
    img, ent = board(rng, W, H)
    px_mm = float(np.clip(rng.normal(8.5, 0.9), 6.5, 11))
    sunny = rng.random() < 0.55
    sun_ang, sun_len = rng.uniform(0, 2 * np.pi), (rng.uniform(1, 6) if sunny else rng.uniform(0, 1.5)) * px_mm
    by_cls = {c: [k for k, s in enumerate(lib) if s["cls"] == c and s["kind"] != "real"] for c in CLASSES}
    real = {c: [k for k, s in enumerate(lib) if s["cls"] == c and s["kind"] == "real"] for c in CLASSES}
    want = [("bee", int(rng.poisson(rng.uniform(1, 22))))]
    # v0.3: more distractors; on real photos, wasps and flies were being called hornet or bee
    for c, p, hi in (("hornet", 0.3, 2), ("shb", 0.25, 3), ("other_insect", 0.65, 6)):
        if rng.random() < p:
            want.append((c, int(rng.integers(1, hi + 1))))
    objs = []
    for c, n in want:
        for _ in range(n):
            pool = real[c] if real[c] and rng.random() < REAL_FRAC else by_cls[c]
            s = lib[pool[rng.integers(len(pool))]]
            x, y, head = place(rng, ent, W, H, s["flying"])
            scale = px_mm / REF_PX_MM * (rng.uniform(1.1, 1.6) if s["flying"] else rng.uniform(0.92, 1.08))
            objs.append(dict(s=s, x=x, y=y, ang=head, scale=scale))
    objs.sort(key=lambda o: o["s"]["flying"])  # flyers are closer to the camera: drawn last
    masks, cover = [], np.zeros((H, W), np.float32)
    for o in objs:
        s = o["s"]
        sp = s["rgba"].astype(np.float32) / 255
        n0 = sp.shape[0]
        n = max(5, int(n0 * o["scale"]))
        sp = cv2.resize(sp, (n, n), interpolation=cv2.INTER_AREA)
        M = cv2.getRotationMatrix2D((n / 2, n / 2), np.degrees(o["ang"]), 1.0)
        sp = cv2.warpAffine(sp, M, (n, n), flags=cv2.INTER_LINEAR)
        if s["flying"]:  # motion and defocus blur
            k = int(rng.integers(3, 15))
            ker = np.zeros((k, k), np.float32)
            ker[k // 2] = 1 / k
            ker = cv2.warpAffine(ker, cv2.getRotationMatrix2D((k / 2, k / 2), rng.uniform(0, 180), 1), (k, k))
            sp = cv2.filter2D(sp, -1, ker / max(ker.sum(), 1e-6))
            sp = cv2.GaussianBlur(sp, (0, 0), rng.uniform(0.5, 2.0))
        sp[..., :3] *= rng.uniform(0.85, 1.15)
        x0, y0 = int(o["x"] - n / 2), int(o["y"] - n / 2)
        xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + n), min(H, y0 + n)
        if xa >= xb or ya >= yb:
            continue
        part = sp[ya - y0:yb - y0, xa - x0:xb - x0]
        a = part[..., 3]
        if not s["flying"]:  # contact shadow cast on the board
            dx, dy = int(np.cos(sun_ang) * sun_len), int(np.sin(sun_ang) * sun_len)
            sh = cv2.GaussianBlur(a, (0, 0), 1 + (0 if sunny else 3)) * (0.45 if sunny else 0.25)
            sx, sy = xa + dx, ya + dy
            hx, hy = min(W, sx + sh.shape[1]) - sx, min(H, sy + sh.shape[0]) - sy
            if sx >= 0 and sy >= 0 and hx > 0 and hy > 0:
                img[sy:sy + hy, sx:sx + hx] *= (1 - sh[:hy, :hx])[..., None]
        img[ya:yb, xa:xb] = part[..., :3] * a[..., None] + img[ya:yb, xa:xb] * (1 - a[..., None])
        full = np.zeros((H, W), np.float32)
        full[ya:yb, xa:xb] = a
        mites = []
        for mx, my in s["mites"]:  # mite centres in scene coords
            px, py = mx * o["scale"] - n0 * o["scale"] / 2, my * o["scale"] - n0 * o["scale"] / 2
            c, sn = np.cos(-o["ang"]), np.sin(-o["ang"])
            mites.append((o["x"] + px * c - py * sn, o["y"] + px * sn + py * c))
        masks.append((o, full, mites))
    # visibility, top object first
    cover[:] = 0
    labels = []
    for o, full, mites in reversed(masks):
        vis = full * (1 - cover)
        cover = cover + full * (1 - cover)
        tot = full.sum()
        if tot < 1:
            continue
        ys, xs = np.nonzero(vis > 0.3)
        frac = float(vis.sum() / tot)
        if len(xs) == 0:
            continue
        vm = [m for m in mites if 0 <= int(m[1]) < H and 0 <= int(m[0]) < W and cover[int(m[1]), int(m[0])] - full[int(m[1]), int(m[0])] < 0.5]
        labels.append(dict(cls=o["s"]["cls"], kind=o["s"]["kind"], box=[int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
                           visible=round(frac, 3), flying=bool(o["s"]["flying"]), pollen=bool(o["s"]["pollen"]),
                           n_mites=len(o["s"]["mites"]), n_mites_visible=len(vm)))
    # lighting: one illuminant for the whole frame, partial hood shade, vignetting
    gain = rng.uniform(0.55, 1.25) * (1.0 if sunny else 0.8)
    warm = rng.uniform(-0.12, 0.12)
    img *= gain * np.float32([1 + warm, 1, 1 - warm])
    if rng.random() < 0.5:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        a0 = rng.uniform(0, 2 * np.pi)
        edge = (xx * np.cos(a0) + yy * np.sin(a0)) / max(W, H) - rng.uniform(0.2, 0.8)
        img *= (1 - rng.uniform(0.2, 0.5) / (1 + np.exp(-edge * rng.uniform(8, 40))))[..., None]
    img *= 1 + 0.08 * render._noise(rng, H, W, 400)[..., None]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r2 = ((xx - W / 2) ** 2 + (yy - H / 2) ** 2) / (W * W / 4 + H * H / 4)
    img *= (1 - rng.uniform(0, 0.3) * r2)[..., None]
    # camera: defocus, sensor noise, white balance error, sharpening
    img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.3, 1.0))
    img = img + rng.normal(0, 1, img.shape).astype(np.float32) * np.sqrt(np.clip(img, 0, 1) * rng.uniform(5e-4, 4e-3) + rng.uniform(1e-5, 1e-4))
    img *= rng.uniform(0.95, 1.05, 3).astype(np.float32)
    if rng.random() < 0.4:
        img = cv2.addWeighted(img, 1.5, cv2.GaussianBlur(img, (0, 0), 1.5), -0.5, 0)
    frame = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    return frame, labels, dict(px_mm=px_mm, sunny=sunny, entrance=ent["side"], debris=ent["debris"])


def crop(frame, box, pad=0.15, size=128):
    x0, y0, x1, y1 = box
    c, s = ((x0 + x1) / 2, (y0 + y1) / 2), max(x1 - x0, y1 - y0) * (1 + 2 * pad)
    M = np.float32([[size / s, 0, size / 2 - c[0] * size / s], [0, size / s, size / 2 - c[1] * size / s]])
    return cv2.warpAffine(frame, M, (size, size), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_REFLECT)


def _write(args):
    i, seed, split, out = args
    frame, labels, meta = scene(i, seed, LIB[split])
    rng = np.random.default_rng([seed, i, 99])
    name = f"{split}_{i:06d}"
    q = int(rng.integers(70, 96))
    small = cv2.resize(frame, STAGE1, interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(out / "stage1/images" / split / f"{name}.jpg"), cv2.cvtColor(small, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, q])
    sx, sy = STAGE1[0] / FULL[0], STAGE1[1] / FULL[1]
    rows, lines = [], []
    for k, lb in enumerate(labels):
        x0, y0, x1, y1 = lb["box"]
        w, h = (x1 - x0) * sx, (y1 - y0) * sy
        if lb["visible"] >= 0.3 and w >= 3 and h >= 3:
            lines.append(f"{CLASSES.index(lb['cls'])} {(x0 + x1) / 2 / FULL[0]:.6f} {(y0 + y1) / 2 / FULL[1]:.6f} {(x1 - x0) / FULL[0]:.6f} {(y1 - y0) / FULL[1]:.6f}")
        row = dict(image=name, split=split, obj=k, **lb, **meta)
        if lb["cls"] == "bee" and not lb["flying"] and lb["visible"] >= 0.7:
            c = crop(frame, lb["box"])
            row["sharpness"] = float(cv2.Laplacian(cv2.cvtColor(c, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var())
            sub = "varroa" if lb["n_mites_visible"] > 0 else "clean"
            cv2.imwrite(str(out / "stage2" / split / sub / f"{name}_{k:02d}.jpg"), cv2.cvtColor(c, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 95])
            row["crop"] = f"stage2/{split}/{sub}/{name}_{k:02d}.jpg"
        rows.append(row)
    (out / "stage1/labels" / split / f"{name}.txt").write_text("\n".join(lines))
    return rows


LIB = {}
REAL_FRAC = 0.0  # share of insects drawn from real-photo cutouts when a class has any
DR_FRAC = 0.0  # share of scenes on a random texture instead of a board


def _init(lib, real_frac=0.0, dr_frac=0.0):
    global REAL_FRAC, DR_FRAC
    REAL_FRAC, DR_FRAC = real_frac, dr_frac
    cv2.setNumThreads(1)
    LIB.update(lib)


def main(out: Path, n: int, seed: int, val_frac: float, workers: int, cutouts: list[Path] = (),
         real_frac: float = 0.5, dr_frac: float = 0.15):
    cv2.setNumThreads(1)  # no OpenCV worker threads in the parent: forking with live threads deadlocks the pool
    for d in ["stage1/images/train", "stage1/images/val", "stage1/labels/train", "stage1/labels/val",
              "stage2/train/varroa", "stage2/train/clean", "stage2/val/varroa", "stage2/val/clean"]:
        (out / d).mkdir(parents=True, exist_ok=True)
    lib = {"train": build_library("train", seed, workers), "val": build_library("val", seed + 10_000, workers)}
    if cutouts:
        for split in lib:
            for folder in cutouts:
                lib[split] += load_cutouts(folder, split)
    else:
        real_frac = 0.0
    n_val = int(n * val_frac)
    jobs = [(i, seed, "val" if i < n_val else "train", out) for i in range(n)]
    with Pool(workers, initializer=_init, initargs=(lib, real_frac, dr_frac)) as p:
        rows = [r for rs in p.imap_unordered(_write, jobs, chunksize=8) for r in rs]
    df = pd.DataFrame(rows)
    df["box"] = df["box"].map(json.dumps)
    df.to_parquet(out / "objects.parquet", index=False)
    (out / "stage1/data.yaml").write_text(
        f"path: {out.resolve() / 'stage1'}\ntrain: images/train\nval: images/val\nnames:\n" +
        "".join(f"  {k}: {c}\n" for k, c in enumerate(CLASSES)))
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    counts = df.groupby(["split", "cls"]).size().unstack(fill_value=0)
    crops = df.dropna(subset=["crop"]).assign(v=lambda d: d.crop.str.contains("/varroa/")).groupby(["split", "v"]).size()
    (out / "DATASET_CARD.md").write_text(f"""# {out.name}

Tier: S (synthetic). Generator: simulation.images.compose v{VERSION} @ git {commit}, seed {seed}.
Images: {n} scenes at {FULL[0]}x{FULL[1]} (stage 1 saved at {STAGE1[0]}x{STAGE1[1]}), {n_val} in val.
Train and val use different procedural sprite libraries (seeds {seed} and {seed + 10_000}).
Real-photo cutouts: {"none" if not cutouts else f"{', '.join(map(str, cutouts))} (share of insects {real_frac}; 1 in 5 files reserved for val; licenses in each manifest.tsv)"}.
Random-texture backgrounds: {dr_frac:.0%} of scenes.
Assets: {"none external. Every insect, board and stain is procedural, so the dataset has no third-party license." if not cutouts else "procedural, plus CC0/CC-BY iNaturalist cutouts listed with source and license in the cutouts manifest."}

Objects per split and class:

{counts.to_markdown()}

Stage 2 crops (True = at least one visible mite):

{crops.to_frame('n').to_markdown()}

Intended use: training and validating the stage 1 detector and the stage 2 Varroa classifier.
Not intended for: claiming real-world performance (use the tier P set).
Known gaps: daylight only; no rain on the lens; no real backgrounds yet (tier C captures go in v0.2+).
""")
    print(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--val-frac", type=float, default=0.15)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--cutouts", type=Path, nargs="*", default=[], help="folders from simulation/images/cutouts.py (real-photo insects)")
    ap.add_argument("--real-frac", type=float, default=0.5)
    ap.add_argument("--dr-frac", type=float, default=0.15)
    a = ap.parse_args()
    main(a.out, a.n, a.seed, a.val_frac, a.workers, a.cutouts, a.real_frac, a.dr_frac)
