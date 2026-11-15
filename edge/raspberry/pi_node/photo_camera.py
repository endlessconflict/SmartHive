"""Mock camd + visiond from your own photos, until the camera and the vision runtime are on the Pi.

Each shot takes one photo from `photos_dir` and leaves it in `frames_dir` as a frame, exactly as visiond does
(`<uuid7>.jpg`, then `<uuid7>.json` with the detections; see frames.py). No picture is ever generated.

What a photo shows comes from where it is:

    photos/                  bees only (no detections): the background frames
    photos/hornet/           a hornet;  photos/shb/  a small hive beetle;  photos/varroa/  a Varroa-positive bee
    photos/<x>.json          optional, next to a photo: its exact detections, which win over the folder
                             {"objects": [{"cls": "hornet", "conf": 0.8, "box": [x1, y1, x2, y2]}]}

A folder detection gets a confidence between 0.60 and 0.95 and a box around the middle of the photo.
Photos are converted to JPEG, like camd's stills (PNG works too). Threats come as visits: with probability
`visit_rate` per frame a visit of `visit_frames` frames starts, where most frames show the visitor, so the
k-of-n rule sees what a real hornet in front of the entrance would give.
"""

import io
import json
import os
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pi_node import payload

PEST_FOLDERS = ("hornet", "shb", "varroa")
SUFFIXES = (".jpg", ".jpeg", ".png")


@dataclass(frozen=True)
class Photo:
    path: Path
    jpeg: bytes
    width: int
    height: int
    objects: list[dict]


def _load(path: Path, cls: str | None, rng: random.Random) -> Photo:
    from PIL import Image  # only the mock needs Pillow

    with Image.open(path) as im:
        rgb = im.convert("RGB")
        buf = io.BytesIO()
        rgb.save(buf, "JPEG", quality=90)
        w, h = rgb.size
    sidecar = path.with_suffix(".json")
    if sidecar.exists():
        objects = list(json.loads(sidecar.read_text())["objects"])
    elif cls is not None:
        objects = [{"cls": cls, "conf": None, "box": [w * 0.25, h * 0.25, w * 0.75, h * 0.75]}]  # conf per shot
    else:
        objects = []
    return Photo(path, buf.getvalue(), w, h, objects)


class PhotoCamera:
    def __init__(self, photos_dir: Path, frames_dir: Path, rng: random.Random | None = None,
                 visit_rate: float = 0.03, visit_frames: int = 10) -> None:
        self.rng = rng or random.Random()
        self.frames_dir = frames_dir
        self.visit_rate = visit_rate
        self.visit_frames = visit_frames
        self.background: list[Photo] = []
        self.pests: dict[str, list[Photo]] = {}
        for path in sorted(photos_dir.rglob("*")):
            if path.suffix.lower() not in SUFFIXES or not path.is_file():
                continue
            folder = path.parent.name.lower() if path.parent != photos_dir else None
            cls = folder if folder in PEST_FOLDERS else None
            photo = _load(path, cls, self.rng)
            if cls is not None or any(o["cls"] in PEST_FOLDERS for o in photo.objects):
                self.pests.setdefault(cls or photo.objects[0]["cls"], []).append(photo)
            else:
                self.background.append(photo)
        if not self.background and not self.pests:
            raise ValueError(f"no .jpg or .png photos in {photos_dir}")
        self._visit: tuple[str, int] | None = None  # (class, frames left)
        frames_dir.mkdir(parents=True, exist_ok=True)

    def _pick(self) -> Photo:
        if self._visit is None and self.pests and self.rng.random() < self.visit_rate:
            self._visit = (self.rng.choice(sorted(self.pests)), self.visit_frames)
        if self._visit is not None:
            cls, left = self._visit
            self._visit = (cls, left - 1) if left > 1 else None
            if self.rng.random() < 0.7 or not self.background:  # the visitor is in most frames of the visit
                return self.rng.choice(self.pests[cls])
        return self.rng.choice(self.background or [p for ps in self.pests.values() for p in ps])

    def shoot(self) -> Path:
        """Leave one frame for the filter; returns its .json path."""
        photo = self._pick()
        objects = [
            {**o, "conf": round(self.rng.uniform(0.60, 0.95), 3) if o["conf"] is None else o["conf"]}
            for o in photo.objects
        ]
        frame_id = payload.uuid7()
        jpg = self.frames_dir / f"{frame_id}.jpg"
        jpg.write_bytes(photo.jpeg)
        info = {"captured_at": payload.iso(datetime.now(UTC)), "clock_synced": True, "width": photo.width,
                "height": photo.height, "objects": objects, "source": photo.path.name}
        sidecar = self.frames_dir / f"{frame_id}.json"
        tmp = sidecar.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(info))
        os.replace(tmp, sidecar)  # last: a .json means the frame is complete
        return sidecar
