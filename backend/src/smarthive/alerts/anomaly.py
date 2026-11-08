"""What counts as an anomaly (US17), as a pure function of a hive's hourly means.

A hive is compared with itself: each recent hourly mean is scored against the same hive's previous days with a
robust z-score, (value - median) / (1.4826 * MAD). The MAD has a floor per quantity, so a very steady
baseline does not turn sensor noise into anomalies. An anomaly is a run of at least `min_run_hours`
consecutive hours on the same side of the baseline, all at or above `info_z`, that is still going on.

| Level     | Peak |z|      | Shown as        |
|-----------|---------------|-----------------|
| `info`    | >= info_z (3.5) | Unusual       |
| `warning` | >= warning_z (6) | Very unusual |

Never critical, and never a notification: an anomaly is something to look at on the next visit, not an
emergency. Known problems with a clear meaning (out of range, hornets, weight drop) have their own rules.

Weight is scored as its hourly change (kg/h), so a heavy hive is not an anomaly but a sudden gain or loss is.
"""

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

HOUR = timedelta(hours=1)
MODEL = "robust-z@1"  # its name in the anomalies table, next to the ML models of US16
QUANTITIES = ("temp_in", "rh_in", "weight")
LABELS = {"temp_in": "Temperature", "rh_in": "Humidity", "weight": "Weight change"}
UNITS = {"temp_in": "°C", "rh_in": "%", "weight": "kg/h"}
DEFAULTS: dict[str, Any] = {
    "baseline_days": 7,
    "recent_hours": 24,  # a run is looked for in this many latest hours; the rest is the baseline
    "min_baseline_hours": 48,  # a hive with less history is not scored
    "min_run_hours": 2,
    "info_z": 3.5,
    "warning_z": 6.0,
    "min_scale_temp_in": 0.3,  # °C
    "min_scale_rh_in": 1.5,  # % RH
    "min_scale_weight": 0.1,  # kg/h
}


@dataclass(frozen=True)
class Bucket:
    ts: datetime  # start of the hour
    value: float


@dataclass(frozen=True)
class Anomaly:
    quantity: str
    level: str  # info | warning
    start: datetime
    end: datetime  # end of the last unusual hour
    value: float  # mean over the run
    expected: float  # the baseline median
    z: float  # the peak, signed: above (+) or below (-) the baseline

    @property
    def direction(self) -> str:
        return "high" if self.z > 0 else "low"

    @property
    def kind(self) -> str:
        """`kind` in the anomalies table, e.g. temp_in_high: tells the dashboard which chart it belongs to."""
        return f"{self.quantity}_{self.direction}"

    def title(self) -> str:
        word = {"temp_in": ("high", "low"), "rh_in": ("high", "low"), "weight": ("gain", "loss")}[
            self.quantity
        ]
        unusual = "Very unusual" if self.level == "warning" else "Unusual"
        what = word[0] if self.z > 0 else word[1]
        if self.quantity == "weight":
            return f"{unusual} weight {what}"
        return f"{unusual}ly {what} {LABELS[self.quantity].lower()}"

    def details(self) -> dict[str, Any]:
        return {
            "kind": "anomaly",
            "quantity": self.quantity,
            "level": self.level,
            "direction": self.direction,
            "window_start": self.start.isoformat(),
            "window_end": self.end.isoformat(),
            "value": round(self.value, 2),
            "expected": round(self.expected, 2),
            "unit": UNITS[self.quantity],
            "z": round(self.z, 1),
            "hours": round((self.end - self.start) / HOUR),
        }


def hourly_changes(buckets: list[Bucket]) -> list[Bucket]:
    """kg/h between consecutive hours; a gap breaks the chain instead of averaging over it."""
    return [
        Bucket(b.ts, b.value - a.value)
        for a, b in zip(buckets, buckets[1:], strict=False)
        if b.ts - a.ts == HOUR
    ]


def score(quantity: str, buckets: list[Bucket], now: datetime, params: dict[str, Any]) -> Anomaly | None:
    """The anomaly going on now in these hourly means (oldest first), or None."""
    p = {**DEFAULTS, **params}
    series = hourly_changes(buckets) if quantity == "weight" else buckets
    cutoff = now - timedelta(hours=p["recent_hours"])
    oldest = now - timedelta(days=p["baseline_days"])
    baseline = [b.value for b in series if oldest <= b.ts < cutoff]
    recent = [b for b in series if b.ts >= cutoff]
    if len(baseline) < p["min_baseline_hours"] or not recent:
        return None
    if now - recent[-1].ts > 2 * HOUR:
        return None  # no fresh data: that is node_offline's business, not an anomaly
    median = statistics.median(baseline)
    mad = statistics.median(abs(v - median) for v in baseline)
    scale = max(1.4826 * mad, float(p[f"min_scale_{quantity}"]))

    run: list[tuple[Bucket, float]] = []
    for b in reversed(recent):  # the unusual hours that end with the latest one
        z = (b.value - median) / scale
        if (
            abs(z) < p["info_z"]
            or (run and (z > 0) != (run[-1][1] > 0))
            or (run and run[-1][0].ts - b.ts != HOUR)
        ):
            break
        run.append((b, z))
    if len(run) < p["min_run_hours"]:
        return None
    run.reverse()
    peak = max((z for _, z in run), key=abs)
    return Anomaly(
        quantity=quantity,
        level="warning" if abs(peak) >= p["warning_z"] else "info",
        start=run[0][0].ts,
        end=run[-1][0].ts + HOUR,
        value=statistics.fmean(b.value for b, _ in run),
        expected=median,
        z=peak,
    )
