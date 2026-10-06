import numpy as np

from simulation.images import compose, render


def _lib():
    jobs = [(i, "bee") for i in range(12)] + [(100 + i, c) for i, c in enumerate(["hornet", "shb", "other_insect"] * 2)]
    return [compose._sprite(j) for j in jobs]


def test_scene_is_deterministic_and_labels_are_sane():
    lib = _lib()
    f1, l1, m1 = compose.scene(3, 9, lib)
    f2, l2, _ = compose.scene(3, 9, lib)
    assert np.array_equal(f1, f2) and l1 == l2
    H, W = f1.shape[:2]
    assert (W, H) == compose.FULL and 6.5 <= m1["px_mm"] <= 11
    for lb in l1:
        x0, y0, x1, y1 = lb["box"]
        assert 0 <= x0 < x1 <= W and 0 <= y0 < y1 <= H
        assert 0 < lb["visible"] <= 1 and lb["n_mites_visible"] <= lb["n_mites"]
        assert lb["cls"] in compose.CLASSES


def test_varroa_is_drawn_at_physical_scale():
    px_mm = 10.0
    for seed in range(5):
        cv = render.Canvas(81)
        render.varroa(cv, np.random.default_rng(seed), 0, 0, px_mm, 0.0)
        ys, xs = np.nonzero(cv.a > 0.5)
        wide, long = max(np.ptp(xs), np.ptp(ys)) + 1, min(np.ptp(xs), np.ptp(ys)) + 1
        assert 1.3 * px_mm <= wide <= 1.9 * px_mm and 0.8 * px_mm <= long <= 1.3 * px_mm  # 1.6 x 1.1 mm


def test_bee_sprite_reports_its_mites():
    rng = np.random.default_rng(0)
    img, info = render.render(rng, render.sample_species(rng, "bee"), 10.0, mites=2)
    assert len(info["mites_px"]) == 2
    for x, y in info["mites_px"]:  # every mite lands on the bee, not beside it
        assert img[int(y), int(x), 3] > 0.5
