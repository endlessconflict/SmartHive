"""Sliding-window limiter for failed logins."""

import time
from collections import defaultdict, deque
from collections.abc import Callable


class FailureLimiter:
    """Counts failures per key inside a window. In memory, so it holds per process.

    ponytail: one API process is all the demo needs. With several, move the counters to PostgreSQL.
    """

    def __init__(self, max_failures: int, window_s: float, clock: Callable[[], float] | None = None) -> None:
        self.max_failures = max_failures
        self.window_s = window_s
        self._clock = clock or time.monotonic
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque[float]:
        events = self._failures[key]
        horizon = self._clock() - self.window_s
        while events and events[0] <= horizon:
            events.popleft()
        if not events:
            self._failures.pop(key, None)
        return events

    def blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= self.max_failures

    def retry_after(self, key: str) -> int:
        events = self._prune(key)
        return max(1, int(events[0] + self.window_s - self._clock()) + 1) if events else 0

    def fail(self, key: str) -> None:
        self._prune(key)
        self._failures[key].append(self._clock())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
