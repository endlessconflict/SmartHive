import json
from datetime import UTC, datetime, timedelta

from pi_node.episodes import Episodes
from pi_node.retention import Detection

T0 = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
BOX = (0.0, 0.0, 10.0, 10.0)


def hornet(conf: float = 0.8) -> list[Detection]:
    return [Detection("hornet", conf, BOX)]


def feed(ep: Episodes, frames: list[list[Detection]], start: datetime = T0, step_s: float = 2) -> list[dict]:
    out = []
    for i, objects in enumerate(frames):
        for body in ep.observe(f"img-{i}", start + timedelta(seconds=i * step_s), objects):
            out.append(json.loads(body))
    return out


def test_three_hornet_frames_in_ten_open_one_episode_naming_the_best_frame() -> None:
    ep = Episodes("node-0001", "boot-1")
    events = feed(ep, [hornet(0.7), [], hornet(0.9), [], hornet(0.75)])
    [e] = events
    assert e["schema"] == "smarthive.event/1.0" and e["node_id"] == "node-0001" and e["boot_id"] == "boot-1"
    body = e["event"]
    assert (body["type"], body["cls"], body["image_id"]) == ("threat_detected", "hornet", "img-2")
    assert (body["frames_positive"], body["frames_window"], body["max_conf"]) == (3, 10, 0.9)
    assert body["first_seen"] == "2026-11-14T12:00:00.000Z" and body["last_seen"] == "2026-11-14T12:00:08.000Z"


def test_two_frames_or_weak_ones_are_not_an_episode() -> None:
    assert feed(Episodes("n", "b"), [hornet(), [], hornet()]) == []
    assert feed(Episodes("n", "b"), [hornet(0.44)] * 10) == []  # below the hornet threshold
    assert feed(Episodes("n", "b"), [hornet(), *[[]] * 9, hornet(), *[[]] * 9, hornet()]) == []  # 1 in 10


def test_a_small_hive_beetle_needs_two_of_ten() -> None:
    [e] = feed(Episodes("n", "b"), [[Detection("shb", 0.6, BOX)]] * 2)
    assert e["event"]["cls"] == "shb"


def test_a_hornet_that_stays_updates_the_same_episode_at_most_once_a_minute() -> None:
    events = feed(Episodes("n", "b"), [hornet()] * 70, step_s=2)  # 140 s of hornet
    ids = {e["event"]["episode_id"] for e in events}
    assert len(ids) == 1 and len(events) == 3  # opened at 4 s, updated at 64 s and 124 s
    assert events[-1]["event"]["last_seen"] > events[0]["event"]["last_seen"]


def test_ten_minutes_without_it_starts_a_new_episode() -> None:
    ep = Episodes("n", "b")
    first = feed(ep, [hornet()] * 3)
    later = feed(ep, [hornet()] * 3, start=T0 + timedelta(minutes=11))
    assert len(first) == len(later) == 1
    assert first[0]["event"]["episode_id"] != later[0]["event"]["episode_id"]
