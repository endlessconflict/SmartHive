"""The filter between vision and the SD card (US08).

visiond, or a fake camera, leaves each analyzed frame in `frames_dir`, a tmpfs (RAM), as two files:

    <frame id>.jpg    the full frame
    <frame id>.json   {"captured_at": "...Z", "clock_synced": true, "width": 1640, "height": 1232,
                       "objects": [{"cls": "hornet", "conf": 0.81, "box": [x1, y1, x2, y2]}, ...]}

The .json is written last (write a temporary name, then rename), so a .json means the .jpg is complete. The
frame id should be a UUIDv7: it becomes the image_id, and processing the same frame twice then queues it once.

A frame the retention rule keeps is copied to `image_dir` on the SD card and queued in the outbox for upload,
with its detections; the crops are not stored, they are cut from the frame with the boxes. A discarded frame is
deleted from RAM and never written to the card.
"""

import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pi_node import payload
from pi_node.outbox import Outbox
from pi_node.retention import Detection, Retention

log = logging.getLogger("pi_node")

ORPHAN_AGE_S = 3600


@dataclass
class FrameStats:
    seen: int = 0
    kept: int = 0
    bytes_seen: int = 0
    bytes_kept: int = 0


def _image_id(stem: str) -> str:
    try:
        return str(uuid.UUID(stem))
    except ValueError:
        return payload.uuid7()


def _write_durably(target: Path, data: bytes) -> None:
    tmp = target.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())  # on the card before the outbox row that points at it
    os.replace(tmp, target)


class FrameFilter:
    def __init__(self, node_id: str, frames_dir: Path, image_dir: Path, outbox: Outbox, retention: Retention) -> None:
        self.node_id = node_id
        self.frames_dir = frames_dir
        self.image_dir = image_dir
        self.outbox = outbox
        self.retention = retention
        self.stats = FrameStats()
        frames_dir.mkdir(parents=True, exist_ok=True)
        image_dir.mkdir(parents=True, exist_ok=True)

    def process(self, limit: int = 50) -> int:
        """Decide on the frames waiting in RAM, oldest name first. Returns how many were handled."""
        handled = 0
        for sidecar in sorted(self.frames_dir.glob("*.json"))[:limit]:
            try:
                self._one(sidecar, sidecar.with_suffix(".jpg"))
            except OSError as e:  # e.g. another process still has the file open (Windows); retried next pass
                log.warning("frame %s not handled yet: %s", sidecar.stem, e)
                continue
            handled += 1
        return handled

    def _one(self, sidecar: Path, jpg: Path) -> None:
        try:
            info = json.loads(sidecar.read_bytes())
            objects = [Detection(str(o["cls"]), float(o["conf"]), tuple(o["box"])) for o in info.get("objects", [])]
            captured_at = datetime.fromisoformat(info["captured_at"].replace("Z", "+00:00"))
            data = jpg.read_bytes()
        except (OSError, ValueError, KeyError, TypeError):
            log.warning("unreadable frame %s, dropped", sidecar.stem)
            self._remove(jpg, sidecar)
            return
        self.stats.seen += 1
        self.stats.bytes_seen += len(data)
        reason = self.retention.decide(objects)
        if reason is not None:
            self._keep(sidecar.stem, data, captured_at, bool(info.get("clock_synced", False)), info, objects, reason)
        self._remove(jpg, sidecar)  # the .json last: while it is there, the frame is retried

    def _keep(self, stem: str, data: bytes, captured_at: datetime, clock_synced: bool, info: dict,
              objects: list[Detection], reason: str) -> None:
        image_id = _image_id(stem)
        sha = hashlib.sha256(data).hexdigest()
        meta = {
            "image_id": image_id,
            "node_id": self.node_id,
            "captured_at": payload.iso(captured_at.astimezone(UTC)),
            "clock_synced": clock_synced,
            "reason": reason,
            "sha256": sha,
            "width": info.get("width"),
            "height": info.get("height"),
            "objects": [{"cls": o.cls, "conf": round(o.conf, 3), "box": list(o.box)} for o in objects],
        }
        target = self.image_dir / f"{image_id}.jpg"
        _write_durably(target, data)
        if self.outbox.add_image(image_id, target, sha, len(data), captured_at, reason, json.dumps(meta).encode()):
            self.stats.kept += 1
            self.stats.bytes_kept += len(data)
            log.info("kept %s (%s, %d KB)", image_id, reason, len(data) // 1024)

    @staticmethod
    def _remove(*paths: Path) -> None:
        for p in paths:
            p.unlink(missing_ok=True)

    def purge(self, older_than: datetime) -> int:
        """Delete images uploaded before that time, and files on the card that no outbox row points at."""
        removed = 0
        for path in self.outbox.purge_images(older_than):
            path.unlink(missing_ok=True)
            removed += 1
        known = self.outbox.image_paths()
        for path in self.image_dir.iterdir():
            # a crash between the file and its row, or mid-write (.tmp); recent ones may still be getting their row
            if path.is_file() and path not in known and time.time() - path.stat().st_mtime > ORPHAN_AGE_S:
                path.unlink(missing_ok=True)
                removed += 1
        return removed
