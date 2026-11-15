"""The mock camera uses only the photos it is given; the full chain then follows the retention rule."""

import io
import json
import random
from pathlib import Path

import pytest

Image = pytest.importorskip("PIL.Image")  # only the mock needs Pillow; CI for the node may not have it

from pi_node.episodes import Episodes  # noqa: E402
from pi_node.frames import FrameFilter  # noqa: E402
from pi_node.outbox import Outbox  # noqa: E402
from pi_node.photo_camera import PhotoCamera  # noqa: E402
from pi_node.retention import Retention, RetentionRule  # noqa: E402


def photo(path: Path, colour: tuple[int, int, int], fmt: str = "PNG") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (160, 280), colour).save(path, fmt)


@pytest.fixture
def photos(tmp_path: Path) -> Path:
    root = tmp_path / "photos"
    photo(root / "bees1.png", (200, 150, 0))
    photo(root / "bees2.jpg", (190, 140, 10), "JPEG")
    photo(root / "hornet" / "h1.png", (90, 40, 0))
    return root


def test_every_frame_is_one_of_the_photos_as_a_jpeg(photos: Path, tmp_path: Path) -> None:
    cam = PhotoCamera(photos, tmp_path / "frames", random.Random(1), visit_rate=0)
    assert len(cam.background) == 2 and list(cam.pests) == ["hornet"]
    sources = set()
    for _ in range(20):
        info = json.loads(cam.shoot().read_text())
        sources.add(info["source"])
        assert (info["width"], info["height"], info["objects"]) == (160, 280, [])
    assert sources == {"bees1.png", "bees2.jpg"}  # no visit: background only
    jpgs = list((tmp_path / "frames").glob("*.jpg"))
    assert len(jpgs) == 20 and all(j.read_bytes().startswith(b"\xff\xd8\xff") for j in jpgs)


def test_a_photo_in_the_hornet_folder_is_a_hornet_and_a_sidecar_wins(photos: Path, tmp_path: Path) -> None:
    (photos / "bees1.json").write_text(json.dumps({"objects": [{"cls": "varroa", "conf": 0.7, "box": [1, 2, 3, 4]}]}))
    cam = PhotoCamera(photos, tmp_path / "frames", random.Random(2), visit_rate=1)
    seen = {}
    for _ in range(40):
        info = json.loads(cam.shoot().read_text())
        seen[info["source"]] = info["objects"]
    [h] = seen["h1.png"]
    assert h["cls"] == "hornet" and 0.6 <= h["conf"] <= 0.95 and h["box"] == [40.0, 70.0, 120.0, 210.0]
    assert seen["bees1.png"] == [{"cls": "varroa", "conf": 0.7, "box": [1, 2, 3, 4]}]  # the sidecar, as is
    assert sorted(cam.pests) == ["hornet", "varroa"]


def test_the_chain_keeps_only_what_the_rule_says_and_raises_the_hornet_event(photos: Path, tmp_path: Path) -> None:
    outbox = Outbox(tmp_path / "outbox.db")
    try:
        cam = PhotoCamera(photos, tmp_path / "frames", random.Random(3), visit_rate=0.05)
        rule = RetentionRule(sample_rate=0, periodic_every_s=None)
        flt = FrameFilter("node-0001", tmp_path / "frames", tmp_path / "images", outbox, Retention(rule),
                          Episodes("node-0001", "boot"))
        for _ in range(300):
            cam.shoot()
            flt.process()
        kept = outbox._db.execute("SELECT image_id, reason, meta FROM images").fetchall()
        assert kept and {r[1] for r in kept} == {"threat"}  # bees only: discarded
        events = [json.loads(r[0]) for r in outbox._db.execute("SELECT payload FROM outbox WHERE kind = 'events'")]
        assert events, "a visit gives at least 3 hornet frames in 10"
        kept_ids = {r[0] for r in kept}
        assert all(e["event"]["image_id"] in kept_ids for e in events)  # the event names an uploaded image
        assert len(list((tmp_path / "frames").iterdir())) == 0  # nothing left in RAM
    finally:
        outbox.close()


def test_a_folder_without_photos_is_refused(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError, match="no .jpg or .png"):
        PhotoCamera(tmp_path / "empty", tmp_path / "frames")


def test_the_jpeg_is_a_real_picture(photos: Path, tmp_path: Path) -> None:
    cam = PhotoCamera(photos, tmp_path / "frames", random.Random(4), visit_rate=0)
    jpg = cam.shoot().with_suffix(".jpg")
    assert Image.open(io.BytesIO(jpg.read_bytes())).size == (160, 280)
