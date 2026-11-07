import hashlib
import json
import os
import random
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pi_node.fake_camera import RELEVANT, FakeCamera, jpeg
from pi_node.frames import ORPHAN_AGE_S, FrameFilter
from pi_node.outbox import Outbox
from pi_node.retention import Retention, RetentionRule

FRAME_ID = "0190f5a2-7c1e-7d43-9a1b-2f6c8e0d4b12"


@pytest.fixture
def node(tmp_path: Path):
    box = Outbox(tmp_path / "outbox.db")
    filt = FrameFilter("node-0001", tmp_path / "frames", tmp_path / "images", box,
                       Retention(RetentionRule(sample_rate=0)))
    yield filt
    box.close()


def leave(frames: Path, objects: list[dict], frame_id: str = FRAME_ID, data: bytes | None = None) -> bytes:
    data = data or jpeg(random.Random(0), 5000)
    (frames / f"{frame_id}.jpg").write_bytes(data)
    (frames / f"{frame_id}.json").write_text(json.dumps({
        "captured_at": "2026-10-06T14:03:21.412Z", "clock_synced": True, "width": 1640, "height": 1232,
        "objects": objects}))
    return data


HORNET = [{"cls": "bee", "conf": 0.9, "box": [1, 2, 3, 4]}, {"cls": "hornet", "conf": 0.8125, "box": [90, 40, 260, 170]}]


def test_a_discarded_frame_never_reaches_the_card(node: FrameFilter) -> None:
    leave(node.frames_dir, [{"cls": "bee", "conf": 0.9, "box": [1, 2, 3, 4]}])
    assert node.process() == 1
    assert list(node.frames_dir.iterdir()) == []
    assert list(node.image_dir.iterdir()) == []
    assert node.outbox.pending_images() == []


def test_a_threat_frame_is_saved_and_queued_with_the_upload_meta(node: FrameFilter) -> None:
    data = leave(node.frames_dir, HORNET)
    node.process()
    [row] = node.outbox.pending_images()
    assert list(node.frames_dir.iterdir()) == []  # out of RAM
    assert row.path == node.image_dir / f"{FRAME_ID}.jpg" and row.path.read_bytes() == data
    assert json.loads(row.meta) == {
        "image_id": FRAME_ID, "node_id": "node-0001", "captured_at": "2026-10-06T14:03:21.412Z",
        "clock_synced": True, "reason": "threat", "sha256": hashlib.sha256(data).hexdigest(),
        "width": 1640, "height": 1232,
        "objects": [{"cls": "bee", "conf": 0.9, "box": [1, 2, 3, 4]},
                    {"cls": "hornet", "conf": 0.812, "box": [90, 40, 260, 170]}],  # the boxes give the crops
    }


def test_the_same_frame_twice_is_queued_once(node: FrameFilter) -> None:
    data = leave(node.frames_dir, HORNET)
    node.process()
    leave(node.frames_dir, HORNET, data=data)  # a crash before the frame was deleted from RAM
    node.process()
    assert len(node.outbox.pending_images()) == 1
    assert node.stats.kept == 1


def test_a_frame_without_a_uuid_name_gets_an_id(node: FrameFilter) -> None:
    leave(node.frames_dir, HORNET, frame_id="frame-0001")
    node.process()
    [row] = node.outbox.pending_images()
    assert row.image_id != "frame-0001" and json.loads(row.meta)["image_id"] == row.image_id


def test_an_unreadable_frame_is_dropped(node: FrameFilter) -> None:
    (node.frames_dir / "bad.jpg").write_bytes(b"x")
    (node.frames_dir / "bad.json").write_text("{not json")
    leave(node.frames_dir, HORNET)
    assert node.process() == 2
    assert list(node.frames_dir.iterdir()) == []
    assert len(node.outbox.pending_images()) == 1


def test_a_frame_still_being_written_is_left_alone(node: FrameFilter) -> None:
    (node.frames_dir / f"{FRAME_ID}.jpg").write_bytes(b"\xff\xd8 half")
    (node.frames_dir / f"{FRAME_ID}.json.tmp").write_text("{}")
    assert node.process() == 0
    assert len(list(node.frames_dir.iterdir())) == 2


def test_a_frame_another_process_holds_open_is_retried(node: FrameFilter, monkeypatch: pytest.MonkeyPatch) -> None:
    leave(node.frames_dir, HORNET)
    real_unlink = Path.unlink

    def busy(self: Path, missing_ok: bool = False) -> None:
        if self.suffix == ".jpg" and self.parent == node.frames_dir:
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", busy)
    assert node.process() == 0  # no crash, and the .json stays so the frame comes back
    assert (node.frames_dir / f"{FRAME_ID}.json").exists()

    monkeypatch.setattr(Path, "unlink", real_unlink)
    assert node.process() == 1
    assert list(node.frames_dir.iterdir()) == []
    assert len(node.outbox.pending_images()) == 1  # kept once, not twice


def test_the_purge_deletes_uploaded_images_and_orphans(node: FrameFilter) -> None:
    leave(node.frames_dir, HORNET)
    node.process()
    [row] = node.outbox.pending_images()
    orphan = node.image_dir / "crashed.tmp"
    orphan.write_bytes(b"x")
    old = time.time() - ORPHAN_AGE_S - 1
    os.utime(orphan, (old, old))
    fresh = node.image_dir / "being-written.jpg"
    fresh.write_bytes(b"x")

    node.outbox.mark_uploaded(row.image_id, datetime.now(UTC) - timedelta(days=4))
    assert node.purge(datetime.now(UTC) - timedelta(days=3)) == 2
    assert list(node.image_dir.iterdir()) == [fresh]
    assert node.outbox.image_counts() == {}


def test_the_purge_keeps_what_is_not_uploaded(node: FrameFilter) -> None:
    leave(node.frames_dir, HORNET)
    node.process()
    assert node.purge(datetime.now(UTC) + timedelta(days=1)) == 0
    assert len(node.outbox.pending_images()) == 1


def test_fake_frames_are_jpegs_of_the_asked_size() -> None:
    data = jpeg(random.Random(1), 200_000)
    assert data[:4] == b"\xff\xd8\xff\xe0" and data.endswith(b"\xff\xd9")
    assert abs(len(data) - 200_000) <= 4
    i = 2
    while data[i + 1] != 0xDA:  # every segment up to the scan is well formed
        assert data[i] == 0xFF
        i += 2 + int.from_bytes(data[i + 2:i + 4], "big")


def test_storage_reduction_on_a_test_run(tmp_path: Path) -> None:
    """US08 check: of a day's worth of motion frames, every relevant one is kept and the card gets a few percent."""
    rng = random.Random(42)
    box = Outbox(tmp_path / "outbox.db")
    camera = FakeCamera(tmp_path / "frames", rng, frame_kb=8)
    filt = FrameFilter("node-0001", tmp_path / "frames", tmp_path / "images", box,
                       Retention(RetentionRule(sample_rate=0.01, max_samples_per_day=24), rng))
    relevant = set()
    for _ in range(2000):
        shot = camera.shoot()
        if shot.scene in RELEVANT:
            relevant.add(shot.frame_id)
        filt.process()
    kept = {r.image_id: r.reason for r in box.pending_images(limit=2000)}
    box.close()

    assert relevant and relevant <= kept.keys()
    assert {kept[i] for i in kept.keys() - relevant} <= {"sample"}
    assert 0 < list(kept.values()).count("sample") <= 24
    assert filt.stats.bytes_kept / filt.stats.bytes_seen < 0.05
    assert sum(p.stat().st_size for p in (tmp_path / "images").iterdir()) == filt.stats.bytes_kept
