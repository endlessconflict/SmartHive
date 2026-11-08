import random
from datetime import UTC, datetime, timedelta

import pytest

from smarthive.alerts.anomaly import HOUR, Bucket, hourly_changes, score

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def hours(
    n: int, mean: float = 35.0, sd: float = 0.1, last: list[float] | None = None, seed: int = 1
) -> list[Bucket]:
    """`n` hourly means ending at the current hour; `last` replaces the newest values."""
    rng = random.Random(seed)
    values = [rng.gauss(mean, sd) for _ in range(n)]
    if last:
        values[-len(last) :] = last
    return [Bucket(NOW - (n - 1 - i) * HOUR, v) for i, v in enumerate(values)]


def test_a_steady_hive_has_no_anomaly() -> None:
    assert score("temp_in", hours(96), NOW, {}) is None


def test_two_unusual_hours_in_a_row_are_an_info_anomaly() -> None:
    found = score("temp_in", hours(96, last=[36.3, 36.4]), NOW, {})
    assert found is not None
    assert (found.level, found.direction) == ("info", "high")
    assert found.start == NOW - HOUR and found.end == NOW + HOUR
    assert found.expected == pytest.approx(35.0, abs=0.05)
    assert found.title() == "Unusually high temperature"
    assert found.details()["hours"] == 2
    assert found.kind == "temp_in_high"


def test_a_large_deviation_is_a_warning_and_never_critical() -> None:
    found = score("temp_in", hours(96, last=[37.5, 38.0, 38.2]), NOW, {})
    assert found is not None and found.level == "warning"
    assert found.title() == "Very unusually high temperature"


def test_one_unusual_hour_is_not_enough() -> None:
    assert score("temp_in", hours(96, last=[37.5]), NOW, {}) is None


def test_the_run_must_still_be_going_on() -> None:
    assert score("temp_in", hours(96, last=[37.5, 37.5, 35.0]), NOW, {}) is None


def test_a_run_changes_side_only_with_a_new_run() -> None:
    found = score("temp_in", hours(96, last=[32.0, 32.0, 38.0, 38.0]), NOW, {})
    assert found is not None and found.direction == "high" and found.start == NOW - HOUR


def test_the_scale_floor_keeps_a_flat_baseline_from_flagging_noise() -> None:
    # a baseline with almost no spread: 0.4 degC would be 40 MADs, but it is under the 0.3 degC floor x 3.5
    assert score("temp_in", hours(96, sd=0.001, last=[35.4, 35.4]), NOW, {}) is None
    assert score("temp_in", hours(96, sd=0.001, last=[36.2, 36.2]), NOW, {}) is not None


def test_a_hive_with_little_history_is_not_scored() -> None:
    assert score("temp_in", hours(60, last=[38.0, 38.0]), NOW, {}) is None  # 36 baseline hours < 48


def test_stale_data_is_not_an_anomaly() -> None:
    old = [Bucket(b.ts - 3 * HOUR, b.value) for b in hours(96, last=[38.0, 38.0])]
    assert score("temp_in", old, NOW, {}) is None


def test_humidity_drop() -> None:
    found = score("rh_in", hours(96, mean=58, sd=0.5, last=[45.0, 44.0]), NOW, {})
    assert found is not None and found.direction == "low" and found.title() == "Very unusually low humidity"


def test_weight_is_scored_by_its_hourly_change() -> None:
    heavy = hours(96, mean=60.0, sd=0.01)
    assert score("weight", heavy, NOW, {}) is None  # a heavy hive is not unusual
    losing = hours(96, mean=41.0, sd=0.01, last=[40.2, 39.4, 38.6])  # 0.8 kg/h, 8 x the 0.1 kg/h floor
    found = score("weight", losing, NOW, {})
    assert found is not None
    assert found.title() == "Very unusual weight loss" and found.details()["unit"] == "kg/h"


def test_a_gap_breaks_the_hourly_change() -> None:
    a, b, c = Bucket(NOW - 3 * HOUR, 41.0), Bucket(NOW - HOUR, 40.0), Bucket(NOW, 39.9)
    [change] = hourly_changes([a, b, c])
    assert change.ts == NOW and change.value == pytest.approx(-0.1)


def test_the_params_override_the_defaults() -> None:
    data = hours(96, last=[36.3, 36.4])
    assert score("temp_in", data, NOW, {"info_z": 10}) is None
    assert score("temp_in", data, NOW, {"min_run_hours": 3}) is None
    found = score("temp_in", data, NOW, {"warning_z": 3})
    assert found is not None and found.level == "warning"


def test_the_window_end_follows_the_last_unusual_hour() -> None:
    found = score("temp_in", hours(96, last=[37.0, 37.0, 37.0]), NOW + timedelta(minutes=30), {})
    assert found is not None and found.end == NOW + HOUR
