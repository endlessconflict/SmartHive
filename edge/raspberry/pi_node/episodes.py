"""Threat episodes from frame detections: the k-of-n rule and the `threat_detected` events (messaging contract).

A class becomes an episode when at least k of the last n analyzed frames have it at or above its threshold
(hornet 3 of 10, shb 2 of 10). The event names the frame with the highest confidence so far as `image_id`;
that frame is a kept image (a threat over its threshold is always kept), so the backend can pair the event
with the upload whichever arrives first. While the threat keeps being seen, a new message with the same
`episode_id` updates `last_seen`, at most once a minute; 10 minutes without a sighting end the episode.

On the Raspberry Pi this is visiond's job. The node runs it only for mock frames (fake_node.py --images).
"""

import json
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pi_node import payload
from pi_node.retention import DEFAULT_THRESHOLDS, Detection

DEFAULT_AGGREGATION = {"hornet": (3, 10), "shb": (2, 10)}
EPISODE_GAP = timedelta(minutes=10)
UPDATE_EVERY = timedelta(minutes=1)
MODELS = {"stage1": "mock-photos@1", "stage2": "mock-photos@1"}


@dataclass
class _Episode:
    episode_id: str
    first_seen: datetime
    last_seen: datetime
    max_conf: float
    image_id: str
    sent_at: datetime  # capture time of the frame that queued the last message


@dataclass
class _Track:
    window: deque[datetime | None]  # per frame: its capture time when positive, else None
    episode: _Episode | None = None
    best: tuple[float, str] | None = None  # (conf, image_id) of the best frame in the window


class Episodes:
    def __init__(self, node_id: str, boot_id: str, thresholds: dict[str, float] | None = None,
                 aggregation: dict[str, tuple[int, int]] | None = None) -> None:
        self.node_id = node_id
        self.boot_id = boot_id
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
        self.aggregation = aggregation or dict(DEFAULT_AGGREGATION)
        self._tracks = {cls: _Track(deque(maxlen=n)) for cls, (_k, n) in self.aggregation.items()}

    def observe(self, image_id: str, captured_at: datetime, objects: Iterable[Detection]) -> list[bytes]:
        """Feed one analyzed frame, in capture order. Returns the event messages to send."""
        objects = list(objects)
        out = []
        for cls, track in self._tracks.items():
            k, n = self.aggregation[cls]
            confs = [o.conf for o in objects if o.cls == cls and o.conf >= self.thresholds[cls]]
            track.window.append(captured_at if confs else None)
            positive = sum(t is not None for t in track.window)
            ep = track.episode
            if ep is not None and captured_at - ep.last_seen >= EPISODE_GAP:
                ep = track.episode = None  # ended; a new sighting starts a new episode
            if not confs:
                if positive == 0:
                    track.best = None
                continue
            conf = max(confs)
            if track.best is None or conf > track.best[0]:
                track.best = (conf, image_id)
            if ep is None:
                if positive >= k:
                    first = min(t for t in track.window if t is not None)
                    best_conf, best_id = track.best
                    track.episode = _Episode(payload.uuid7(), first, captured_at, best_conf, best_id, captured_at)
                    out.append(self._message(cls, track.episode, positive, n))
                continue
            ep.last_seen = captured_at
            if conf > ep.max_conf:
                ep.max_conf, ep.image_id = conf, image_id
            if captured_at - ep.sent_at >= UPDATE_EVERY:
                ep.sent_at = captured_at
                out.append(self._message(cls, ep, positive, n))
        return out

    def _message(self, cls: str, ep: _Episode, positive: int, window: int) -> bytes:
        doc = {
            "schema": "smarthive.event/1.0",
            "msg_id": payload.uuid7(),
            "node_id": self.node_id,
            "boot_id": self.boot_id,
            "sent_at": payload.iso(datetime.now(UTC)),
            "event": {
                "type": "threat_detected",
                "episode_id": ep.episode_id,
                "cls": cls,
                "first_seen": payload.iso(ep.first_seen),
                "last_seen": payload.iso(ep.last_seen),
                "clock_synced": True,
                "max_conf": round(ep.max_conf, 3),
                "frames_positive": positive,
                "frames_window": window,
                "image_id": ep.image_id,
                "models": MODELS,
            },
        }
        return json.dumps(doc, separators=(",", ":")).encode()
