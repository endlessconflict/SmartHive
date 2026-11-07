"""Which analyzed frames are kept (US08). The rest are deleted from the tmpfs and never reach the SD card.

In order, the first rule that matches wins:

1. a threat (hornet, shb) at or above its class threshold  -> reason "threat"
2. a Varroa-positive bee at or above the varroa threshold  -> reason "varroa"
3. otherwise, a random `sample_rate` of the frames, at most `max_samples_per_day` -> reason "sample"
4. otherwise the frame is discarded

The random sample is what lets someone check what the filter throws away: false negatives, and real
backgrounds for retraining (ADR-0002). It is drawn from every frame that rules 1 and 2 did not keep, near misses
included. Bees, other insects and threats below their threshold are not a reason to keep a frame.
"""

import random
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

THREATS = ("hornet", "shb")
DEFAULT_THRESHOLDS = {"hornet": 0.45, "shb": 0.50, "varroa": 0.60}
DAY_S = 86400.0


@dataclass(frozen=True)
class Detection:
    cls: str
    conf: float
    box: tuple[float, float, float, float]


@dataclass(frozen=True)
class RetentionRule:
    thresholds: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))
    sample_rate: float = 0.01
    max_samples_per_day: int = 24

    def __post_init__(self) -> None:
        if not 0 <= self.sample_rate <= 1:
            raise ValueError("sample_rate must be between 0 and 1")
        missing = {*THREATS, "varroa"} - self.thresholds.keys()
        if missing:
            raise ValueError(f"thresholds missing for {', '.join(sorted(missing))}")


class Retention:
    def __init__(
        self,
        rule: RetentionRule,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.rule = rule
        self.rng = rng or random.Random()
        self.clock = clock
        self._samples: deque[float] = deque()  # when the samples of the last 24 h were kept; a restart forgets them

    def decide(self, objects: Iterable[Detection]) -> str | None:
        """The reason to keep the frame, or None to discard it."""
        objects = list(objects)
        t = self.rule.thresholds
        if any(o.cls in THREATS and o.conf >= t[o.cls] for o in objects):
            return "threat"
        if any(o.cls == "varroa" and o.conf >= t["varroa"] for o in objects):
            return "varroa"
        drawn = self.rng.random() < self.rule.sample_rate  # drawn for every frame, so a seed gives a fixed sequence
        now = self.clock()
        while self._samples and now - self._samples[0] >= DAY_S:
            self._samples.popleft()
        if drawn and len(self._samples) < self.rule.max_samples_per_day:
            self._samples.append(now)
            return "sample"
        return None
