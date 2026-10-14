"""Procedural top-down insect sprites. No photos, no 3D models: every pixel comes from code,
so there is no license question and unlimited variety. Design: docs/03-vision/03-synthetic-image-pipeline.md

One generic segmented-insect renderer (head, thorax, optional waist, abdomen, wings, legs,
antennae, hair, gloss) driven by per-species parameter samplers. Sizes are in millimetres
and converted with px_per_mm, so scale always matches the camera geometry.

    python -m simulation.images.render  # writes a contact sheet to /tmp/sprites.png
"""
import cv2
import numpy as np

SS = 2  # supersampling factor for anti-aliased edges


def _hsv(h, s, v):
    """h in degrees, s/v in 0..1 -> RGB float 0..1."""
    c = cv2.cvtColor(np.uint8([[[h / 2, s * 255, v * 255]]]), cv2.COLOR_HSV2RGB)[0, 0] / 255.0
    return c.astype(np.float32)


def _jit(rng, rgb, amount=0.08):
    return np.clip(rgb * rng.uniform(1 - amount, 1 + amount, 3), 0, 1).astype(np.float32)


def _noise(rng, h, w, scale):
    """Smooth value noise in [-1, 1]."""
    small = rng.uniform(-1, 1, (max(2, int(h / scale)), max(2, int(w / scale)))).astype(np.float32)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)


class Canvas:
    def __init__(self, size):
        self.n = size
        self.rgb = np.zeros((size, size, 3), np.float32)
        self.a = np.zeros((size, size), np.float32)
        yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
        self.x, self.y = xx - size / 2, size / 2 - yy  # body axis +x (head), +y left side

    def over(self, alpha, rgb):
        alpha = np.clip(alpha, 0, 1)[..., None]
        self.rgb = rgb * alpha + self.rgb * (1 - alpha)
        self.a = np.clip(alpha[..., 0] + self.a * (1 - alpha[..., 0]), 0, 1)

    def ellipse_r(self, cx, cy, ax, ay, ang=0.0):
        """Normalized elliptical radius (1 on the outline)."""
        c, s = np.cos(ang), np.sin(ang)
        dx, dy = self.x - cx, self.y - cy
        u, v = (dx * c + dy * s) / ax, (-dx * s + dy * c) / ay
        return np.sqrt(u * u + v * v), u, v

    def line(self, pts, width, rgb, alpha=1.0):
        m = np.zeros((self.n, self.n), np.uint8)
        p = np.array([[self.n / 2 + x, self.n / 2 - y] for x, y in pts], np.int32)
        cv2.polylines(m, [p], False, 255, max(1, int(round(width))), cv2.LINE_AA)
        self.over(m / 255.0 * alpha, np.broadcast_to(rgb, self.rgb.shape))


def body_part(cv, rng, cx, length, width, color, *, bands=(), hair=0.0, hair_rgb=None, gloss=0.3, edge=1.5):
    """Shaded ellipsoid segment along the body axis. bands: [(u0, u1, rgb)] in local -1..1 (tail..head)."""
    r, u, v = cv.ellipse_r(cx, 0, length / 2, width / 2)
    base = np.broadcast_to(color, cv.rgb.shape).copy()
    for u0, u1, rgb in bands:  # transverse stripes, slightly curved like real tergites
        uu = u + 0.12 * v * v
        sel = (uu >= u0) & (uu < u1)
        base[sel] = rgb
    shade = np.clip(1.15 - 0.55 * r ** 2, 0.35, 1.2)[..., None]  # rounded body, darker rim
    tex = 1 + 0.12 * _noise(rng, cv.n, cv.n, width / 3)[..., None]
    col = base * shade * tex
    hl = np.exp(-(((u - 0.15) ** 2 + (v - 0.35) ** 2) / 0.08))[..., None] * gloss  # specular spot
    col = np.clip(col + hl, 0, 1)
    if hair > 0:  # fuzzy setae: speckle + soft, ragged outline
        speck = (rng.random((cv.n, cv.n)) < 0.25 * hair) & (r < 1.05)
        col[speck] = col[speck] * 0.5 + (hair_rgb if hair_rgb is not None else col[speck]) * 0.5
        r = r - hair * 0.12 * _noise(rng, cv.n, cv.n, 2)
    alpha = np.clip((1 - r) * (length / 2) / edge, 0, 1)
    cv.over(alpha, col)
    return r, u, v


def wing(cv, rng, root, length, width, angle, tint, alpha, veins):
    c, s = np.cos(angle), np.sin(angle)
    cx, cy = root[0] + c * length / 2, root[1] + s * length / 2
    r, u, v = cv.ellipse_r(cx, cy, length / 2, width / 2, angle)
    a = np.clip((1 - r) * 6, 0, 1) * alpha * (0.85 + 0.15 * u)
    cv.over(a, np.broadcast_to(tint, cv.rgb.shape))
    for k in range(3):  # a few longitudinal veins
        off = (k - 1) * width * 0.22
        pts = [(root[0] + c * t * length - s * off * t, root[1] + s * t * length + c * off * t) for t in (0.05, 0.5, 0.9)]
        cv.line(pts, max(1, width * 0.025), veins, alpha * 0.6)


def legs(cv, rng, cx, spread, length, width, rgb, pollen=None):
    for side in (1, -1):
        for k, base_ang in enumerate((55, 95, 135)):  # fore, mid, hind legs
            a1 = np.radians(base_ang + rng.uniform(-15, 15)) * side
            a2 = a1 + np.radians(rng.uniform(10, 40)) * side * (1 if k == 2 else -1)
            x0, y0 = cx + (1 - k) * spread * 0.5, side * spread * 0.3
            x1, y1 = x0 + np.cos(a1) * length * 0.5, y0 + np.sin(a1) * length * 0.5
            x2, y2 = x1 + np.cos(a2) * length * 0.55, y1 + np.sin(a2) * length * 0.55
            cv.line([(x0, y0), (x1, y1), (x2, y2)], width, rgb)
            if pollen is not None and k == 2:  # corbicula load on hind legs
                r, *_ = cv.ellipse_r(x1, y1, pollen[1], pollen[1] * 0.8)
                cv.over(np.clip((1 - r) * 4, 0, 1), np.broadcast_to(pollen[0], cv.rgb.shape))


def antennae(cv, cx, length, width, rgb, elbow=False, club=False):
    for side in (1, -1):
        a = np.radians(25) * side
        p1 = (cx + np.cos(a) * length * (0.35 if elbow else 0.5), np.sin(a) * length * (0.35 if elbow else 0.5))
        a2 = a + (np.radians(30) * side if elbow else np.radians(10) * side)
        p2 = (p1[0] + np.cos(a2) * length * 0.65, p1[1] + np.sin(a2) * length * 0.65)
        cv.line([(cx, 0), p1, p2], width, rgb)
        if club:
            r, *_ = cv.ellipse_r(p2[0], p2[1], width * 1.6, width * 1.6)
            cv.over(np.clip((1 - r) * 3, 0, 1), np.broadcast_to(rgb, cv.rgb.shape))


def varroa(cv, rng, cx, cy, px_mm, body_ang):
    """Female Varroa destructor: ~1.1 mm long x 1.6 mm wide, reddish brown, glossy, wider than long."""
    w, l = rng.uniform(1.45, 1.75) * px_mm, rng.uniform(1.0, 1.2) * px_mm
    ang = body_ang + np.pi / 2 + rng.uniform(-0.5, 0.5)  # wide axis roughly across the bee
    col = _hsv(rng.uniform(8, 28), rng.uniform(0.55, 0.9), rng.uniform(0.3, 0.6))
    r, u, v = cv.ellipse_r(cx, cy, w / 2, l / 2, ang)
    shade = np.clip(1.1 - 0.6 * r ** 2, 0.3, 1.1)[..., None]
    hl = np.exp(-(((u + 0.2) ** 2 + (v - 0.3) ** 2) / 0.05))[..., None] * rng.uniform(0.2, 0.6)
    rim = (r > 0.8)[..., None] * 0.25
    cv.over(np.clip((1 - r) * w / 2 / 1.2, 0, 1), np.clip(col * shade * (1 - rim) + hl, 0, 1))


# ---- species parameter samplers (sizes in mm) --------------------------------------------

def _bee(rng, africanized):
    amber = _hsv(rng.uniform(25, 40), rng.uniform(0.6, 0.9), rng.uniform(0.45, 0.8))
    dark = _hsv(rng.uniform(20, 30), rng.uniform(0.4, 0.7), rng.uniform(0.08, 0.2))
    if africanized or rng.random() < 0.3:  # darker, narrower amber bands
        amber = amber * rng.uniform(0.6, 0.85)
    bands, u = [], -1.0
    for k in range(6):
        w = 0.33
        bands.append((u, u + w * 0.65, amber if k >= 2 or rng.random() < 0.6 else dark))
        bands.append((u + w * 0.65, u + w, dark))
        u += w
    return dict(L=rng.uniform(12, 15), head=(0.17, 0.30, dark), thorax=(0.27, 0.34, _hsv(25, 0.5, 0.18)),
                waist=None, abdomen=(0.56, 0.38, amber, bands[::-1]), hair=rng.uniform(0.3, 0.7),
                hair_rgb=_hsv(rng.uniform(30, 40), 0.4, rng.uniform(0.55, 0.8)), gloss=0.2,
                wings=dict(pairs=2, len=0.6, wid=0.12, tint=np.float32([0.75, 0.78, 0.82]), alpha=rng.uniform(0.15, 0.28)),
                legs=dict(len=0.24, wid=0.014, rgb=_hsv(20, 0.5, 0.12)),
                ant=dict(len=0.2, wid=0.018, elbow=True, club=False), eyes=_hsv(20, 0.3, 0.1))


def _hornet(rng, kind):
    brown = _hsv(rng.uniform(15, 25), 0.7, rng.uniform(0.12, 0.25))
    orange = _hsv(rng.uniform(25, 40), rng.uniform(0.75, 1), rng.uniform(0.7, 0.95))
    yellow = _hsv(rng.uniform(42, 52), 0.85, 0.9)
    if kind == "velutina":  # dark abdomen, thin yellow edges, broad orange 4th segment
        bands = [(-1, -0.55, orange), (-0.55, -0.45, yellow), (-0.45, -0.1, brown), (-0.1, -0.05, yellow),
                 (-0.05, 0.3, brown), (0.3, 0.35, yellow), (0.35, 1, brown)]
        thorax = brown
    else:  # crabro-like: yellow abdomen with brown chevrons, reddish thorax
        bands = [(-1, -0.2, yellow), (-0.2, -0.1, brown), (-0.1, 0.25, yellow), (0.25, 0.35, brown), (0.35, 1, _hsv(15, 0.6, 0.35))]
        thorax = _hsv(10, 0.6, 0.35)
    return dict(L=rng.uniform(20, 30), head=(0.15, 0.28, orange), thorax=(0.27, 0.27, thorax),
                waist=(0.04, 0.08), abdomen=(0.52, 0.32, brown, bands), hair=0.15, hair_rgb=brown, gloss=0.35,
                wings=dict(pairs=2, len=0.6, wid=0.14, tint=_hsv(30, 0.5, 0.5), alpha=0.45),
                legs=dict(len=0.32, wid=0.022, rgb=yellow if kind == "velutina" else brown),
                ant=dict(len=0.2, wid=0.02, elbow=True, club=False), eyes=brown)


def _shb(rng):
    col = _hsv(rng.uniform(10, 25), rng.uniform(0.4, 0.8), rng.uniform(0.07, 0.3))  # young beetles are reddish
    return dict(L=rng.uniform(5, 7), head=(0.15, 0.4, col), thorax=(0.25, 0.62, col), waist=None,
                abdomen=(0.62, 0.58, col, [(-0.03, 0.03, col * 0.5)]), hair=0.25, hair_rgb=col * 1.6, gloss=0.6,
                wings=None, legs=dict(len=0.22, wid=0.035, rgb=col * 0.8),
                ant=dict(len=0.16, wid=0.03, elbow=False, club=True), eyes=col * 0.5)


def _other(rng):
    kind = rng.choice(["fly", "ant", "wasp", "bumblebee"])
    if kind == "fly":
        grey = _hsv(30, 0.1, rng.uniform(0.3, 0.5))
        return dict(kind=kind, L=rng.uniform(6, 8), head=(0.2, 0.45, _hsv(10, 0.7, 0.45)), thorax=(0.32, 0.45, grey),
                    waist=None, abdomen=(0.42, 0.45, grey, [(-1, -0.6, grey * 0.6), (-0.3, 0.1, grey * 0.6)]),
                    hair=0.2, hair_rgb=grey * 0.5, gloss=0.3,
                    wings=dict(pairs=1, len=0.75, wid=0.25, tint=np.float32([0.8, 0.8, 0.82]), alpha=0.3),
                    legs=dict(len=0.32, wid=0.03, rgb=grey * 0.4), ant=dict(len=0.1, wid=0.04, elbow=False, club=False),
                    eyes=_hsv(10, 0.8, 0.4))
    if kind == "ant":
        c = _hsv(rng.uniform(5, 30), rng.uniform(0.3, 0.8), rng.uniform(0.08, 0.35))
        return dict(kind=kind, L=rng.uniform(3, 10), head=(0.27, 0.3, c), thorax=(0.3, 0.18, c), waist=(0.08, 0.08),
                    abdomen=(0.38, 0.3, c, []), hair=0.05, hair_rgb=c, gloss=0.5, wings=None,
                    legs=dict(len=0.45, wid=0.03, rgb=c), ant=dict(len=0.3, wid=0.025, elbow=True, club=False), eyes=c * 0.5)
    if kind == "wasp":
        y, b = _hsv(rng.uniform(42, 55), 0.9, 0.9), _hsv(0, 0, 0.08)
        bands = [(u, u + 0.12, b) for u in np.arange(-0.9, 0.9, 0.3)]
        return dict(kind=kind, L=rng.uniform(11, 16), head=(0.16, 0.3, y), thorax=(0.27, 0.28, b), waist=(0.05, 0.07),
                    abdomen=(0.5, 0.32, y, bands), hair=0.05, hair_rgb=b, gloss=0.4,
                    wings=dict(pairs=2, len=0.6, wid=0.13, tint=_hsv(40, 0.3, 0.6), alpha=0.35),
                    legs=dict(len=0.32, wid=0.022, rgb=y), ant=dict(len=0.2, wid=0.02, elbow=True, club=False), eyes=b)
    bk, yl = _hsv(0, 0, 0.07), _hsv(rng.uniform(40, 52), 0.8, 0.85)
    return dict(kind="bumblebee", L=rng.uniform(14, 20), head=(0.16, 0.38, bk), thorax=(0.32, 0.5, yl), waist=None,
                abdomen=(0.52, 0.55, bk, [(0.3, 0.6, yl), (-1, -0.5, np.float32([0.9, 0.9, 0.88]))]),
                hair=0.9, hair_rgb=bk, gloss=0.05,
                wings=dict(pairs=2, len=0.5, wid=0.15, tint=_hsv(30, 0.4, 0.4), alpha=0.4),
                legs=dict(len=0.28, wid=0.03, rgb=bk), ant=dict(len=0.16, wid=0.025, elbow=True, club=False), eyes=bk)


def sample_species(rng, cls):
    if cls == "bee":
        return dict(_bee(rng, africanized=rng.random() < 0.6), kind="bee")
    if cls == "hornet":
        k = "velutina" if rng.random() < 0.6 else "crabro"
        return dict(_hornet(rng, k), kind=k)
    if cls == "shb":
        return dict(_shb(rng), kind="shb")
    return _other(rng)


def render(rng, sp, px_mm, *, angle=0.0, flying=False, mites=0, pollen=False, dead=False):
    """Returns (rgba float32 HxWx4, info). info has mite positions in sprite pixels."""
    L = sp["L"] * px_mm * SS
    n = int(L * 1.6) | 1
    cv = Canvas(n)
    head_l, head_w, head_c = sp["head"]
    th_l, th_w, th_c = sp["thorax"]
    ab_l, ab_w, ab_c, ab_bands = sp["abdomen"]
    wl = sp["waist"][0] if sp["waist"] else 0.0
    total = head_l + th_l + wl + ab_l
    s = L / total
    x_tail = -L / 2
    ab_cx = x_tail + ab_l * s / 2
    w_cx = x_tail + ab_l * s + wl * s / 2
    th_cx = x_tail + (ab_l + wl) * s + th_l * s / 2 - 0.03 * L
    hd_cx = th_cx + th_l * s / 2 + head_l * s / 2 - 0.05 * L
    lg = sp["legs"]
    legs(cv, rng, th_cx, th_w * s, lg["len"] * L * (0.6 if dead else 1), lg["wid"] * L, lg["rgb"],
         pollen=(_hsv(rng.choice([45, 30, 15, 0, 60]), rng.uniform(0.6, 1), rng.uniform(0.5, 0.95)), 0.07 * L) if pollen else None)
    body_part(cv, rng, ab_cx, ab_l * s, ab_w * s, ab_c, bands=ab_bands, hair=sp["hair"] * 0.6, hair_rgb=sp["hair_rgb"], gloss=sp["gloss"])
    if sp["waist"]:
        body_part(cv, rng, w_cx, sp["waist"][0] * s * 1.6, sp["waist"][1] * s, th_c, gloss=sp["gloss"])
    body_part(cv, rng, th_cx, th_l * s, th_w * s, th_c, hair=sp["hair"], hair_rgb=sp["hair_rgb"], gloss=sp["gloss"])
    body_part(cv, rng, hd_cx, head_l * s, head_w * s, head_c, hair=sp["hair"] * 0.5, hair_rgb=sp["hair_rgb"], gloss=sp["gloss"])
    for side in (1, -1):  # compound eyes
        r, *_ = cv.ellipse_r(hd_cx, side * head_w * s * 0.33, head_l * s * 0.4, head_w * s * 0.18)
        cv.over(np.clip((1 - r) * 3, 0, 1), np.broadcast_to(sp["eyes"], cv.rgb.shape))
    mite_xy = []
    for _ in range(mites):  # anchor regions: dorsal thorax and the front 2/3 of the abdomen
        if rng.random() < 0.4:
            cx, cy = th_cx + rng.uniform(-0.25, 0.25) * th_l * s, rng.uniform(-0.25, 0.25) * th_w * s
        else:
            cx, cy = ab_cx + rng.uniform(-0.1, 0.4) * ab_l * s, rng.uniform(-0.3, 0.3) * ab_w * s
        varroa(cv, rng, cx, cy, px_mm * SS, 0.0)
        mite_xy.append((cx, cy))
    if sp["wings"]:
        wg = sp["wings"]
        root = (th_cx + 0.05 * L, 0)
        for side in (1, -1):
            for k in range(wg["pairs"]):
                if flying:
                    ang = np.radians(rng.uniform(60, 130) - 25 * k) * side
                else:
                    ang = np.pi - np.radians(rng.uniform(2, 18) + 6 * k) * side
                wing(cv, rng, (root[0] - 0.04 * L * k, root[1] + side * 0.05 * L), wg["len"] * L * (1 - 0.25 * k),
                     wg["wid"] * L * (1 - 0.2 * k), ang, wg["tint"], wg["alpha"], wg["tint"] * 0.4)
    ant = sp["ant"]
    antennae(cv, hd_cx + head_l * s * 0.4, ant["len"] * L, max(1, ant["wid"] * L), sp["legs"]["rgb"], ant["elbow"], ant["club"])
    rgba = np.dstack([cv.rgb, cv.a])
    # rotate around the sprite centre, then downsample (anti-aliasing)
    Mrot = cv2.getRotationMatrix2D((n / 2, n / 2), np.degrees(angle), 1.0)
    rgba = cv2.warpAffine(rgba, Mrot, (n, n), flags=cv2.INTER_LINEAR)
    out = cv2.resize(rgba, (max(3, n // SS), max(3, n // SS)), interpolation=cv2.INTER_AREA)
    c, s_ = np.cos(angle), np.sin(angle)
    mites_px = [((n / 2 + x * c + y * s_) / SS, (n / 2 + x * s_ - y * c) / SS) for x, y in mite_xy]
    if flying:  # wing beat blur: wings become faint discs, body slightly blurred
        out[..., 3] = np.where(out[..., 3] < 0.5, cv2.GaussianBlur(out[..., 3], (0, 0), max(0.5, L / SS * 0.04)), out[..., 3])
    return out.astype(np.float32), {"mites_px": mites_px}


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    tiles = []
    for cls in ["bee", "bee", "bee", "hornet", "hornet", "shb", "other", "other", "other", "other"]:
        sp = sample_species(rng, cls)
        img, _ = render(rng, sp, 8.5, angle=rng.uniform(0, 6.28), mites=2 if cls == "bee" else 0, pollen=rng.random() < 0.5)
        bg = np.full(img.shape[:2] + (3,), 0.85, np.float32)
        comp = img[..., :3] * img[..., 3:] + bg * (1 - img[..., 3:])
        tiles.append(cv2.resize(comp, (260, 260)))
    sheet = np.vstack([np.hstack(tiles[:5]), np.hstack(tiles[5:])])
    cv2.imwrite("/tmp/sprites.png", cv2.cvtColor((sheet * 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
    print("/tmp/sprites.png")
