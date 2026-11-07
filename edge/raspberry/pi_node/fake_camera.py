"""Synthetic analyzed frames, in the format visiond leaves in the frames directory (see frames.py).

Each frame is a real JPEG (a small picture padded with comment segments to the size of a 1640x1232 still),
so the backend accepts it and can make thumbnails, and its detections come from a fixed scene mix. No camera,
no model, no image library.
"""

import base64
import json
import os
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pi_node import payload

_BASE = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAA0JCgsKCA0LCgsODg0PEyAVExISEyccHhcgLikxMC4pLSwzOko+MzZGNywtQFdBRkxOUlNSMj5a"
    "YVpQYEpRUk//2wBDAQ4ODhMREyYVFSZPNS01T09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0//wAAR"
    "CAAwAEADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEG"
    "E1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWG"
    "h4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEB"
    "AQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYk"
    "NOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0"
    "tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDWoooryDuCiqt5f2tjs+1S7N+dvyk5x16D"
    "3qt/b+l/8/X/AJDb/Cmot7IV0adFZn9v6X/z9f8AkNv8KntNTs72UxW029wu4jaRx+I96OWS6BdFyiiikMKKKKAOa8Yf8uf/AAP/ANlrmq6X"
    "xh/y5/8AA/8A2WuarspfAjKW4VueE/8AkJyf9cT/AOhLWHW54T/5Ccn/AFxP/oS06nwsUdzrqKKK4jYKKKKAKOpaXBqXl+e8i+XnGwgdceo9"
    "qo/8IvY/89bn/vpf8K3KKpTklZMVkYf/AAi9j/z1uf8Avpf8Ktado1tp07TQPKzMu0hyCMZB7D2rSooc5PRsLIKKKKkZ/9k="
)
_AFTER_APP0 = 4 + int.from_bytes(_BASE[4:6], "big")  # SOI, then the APP0 marker and its length
WIDTH, HEIGHT = 1640, 1232
FRAME_KB = 450  # a 1640x1232 JPEG at quality 85 of a hive entrance

# (name, share of motion-triggered frames, relevant?) on a busy entrance by day
SCENES = [
    ("empty", 0.550, False),          # motion with nothing on it: shadows, wind, light
    ("bees", 0.400, False),
    ("hornet_weak", 0.015, False),    # below the hornet threshold
    ("hornet", 0.005, True),
    ("varroa_weak", 0.020, False),    # below the varroa threshold
    ("varroa", 0.010, True),
]
RELEVANT = {name for name, _, relevant in SCENES if relevant}


def jpeg(rng: random.Random, size: int) -> bytes:
    """A valid JPEG of about `size` bytes, different every time."""
    pad = bytearray()
    left = max(0, size - len(_BASE))
    while left > 4:
        n = min(left - 4, 65533)
        pad += b"\xff\xfe" + (n + 2).to_bytes(2, "big") + rng.randbytes(n)
        left -= n + 4
    return _BASE[:_AFTER_APP0] + bytes(pad) + _BASE[_AFTER_APP0:]  # comments after the JFIF header


def _box(rng: random.Random, side: float) -> list[float]:
    x, y = rng.uniform(0, WIDTH - side), rng.uniform(0, HEIGHT - side)
    return [round(x), round(y), round(x + side), round(y + side)]


def objects(scene: str, rng: random.Random) -> list[dict]:
    bees = [{"cls": "bee", "conf": round(rng.uniform(0.5, 0.95), 2), "box": _box(rng, 60)}
            for _ in range(rng.randint(1, 6))]
    match scene:
        case "empty":
            return []
        case "bees":
            return bees
        case "hornet_weak":
            return [*bees, {"cls": "hornet", "conf": round(rng.uniform(0.2, 0.4), 2), "box": _box(rng, 120)}]
        case "hornet":
            return [*bees, {"cls": "hornet", "conf": round(rng.uniform(0.6, 0.9), 2), "box": _box(rng, 120)}]
        case "varroa_weak":
            return [*bees, {"cls": "varroa", "conf": round(rng.uniform(0.3, 0.55), 2), "box": bees[0]["box"]}]
        case "varroa":
            return [*bees, {"cls": "varroa", "conf": round(rng.uniform(0.65, 0.9), 2), "box": bees[0]["box"]}]
    raise ValueError(scene)


@dataclass(frozen=True)
class Shot:
    frame_id: str
    scene: str
    bytes: int


class FakeCamera:
    def __init__(self, frames_dir: Path, rng: random.Random | None = None, frame_kb: float = FRAME_KB) -> None:
        self.frames_dir = frames_dir
        self.rng = rng or random.Random()
        self.frame_kb = frame_kb
        frames_dir.mkdir(parents=True, exist_ok=True)

    def scene(self) -> str:
        return self.rng.choices([s[0] for s in SCENES], weights=[s[1] for s in SCENES])[0]

    def shoot(self, scene: str | None = None) -> Shot:
        """Leave one analyzed frame as visiond would: the .jpg, then the .json under its final name last."""
        scene = scene or self.scene()
        frame_id = payload.uuid7()
        size = int(max(0.4, self.rng.gauss(1, 0.12)) * self.frame_kb * 1024)
        data = jpeg(self.rng, size)
        (self.frames_dir / f"{frame_id}.jpg").write_bytes(data)
        info = {"captured_at": payload.iso(datetime.now(UTC)), "clock_synced": True, "width": WIDTH,
                "height": HEIGHT, "objects": objects(scene, self.rng)}
        tmp = self.frames_dir / f"{frame_id}.json.tmp"
        tmp.write_text(json.dumps(info))
        os.replace(tmp, self.frames_dir / f"{frame_id}.json")
        return Shot(frame_id, scene, len(data))
