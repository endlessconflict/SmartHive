import random

import pytest

from pi_node.retention import DAY_S, Detection, Retention, RetentionRule

BOX = (0.0, 0.0, 10.0, 10.0)
NO_SAMPLE = RetentionRule(sample_rate=0)


def det(cls: str, conf: float) -> Detection:
    return Detection(cls, conf, BOX)


@pytest.mark.parametrize(("cls", "conf"), [("hornet", 0.45), ("hornet", 0.9), ("shb", 0.5)])
def test_a_threat_at_its_threshold_is_kept(cls: str, conf: float) -> None:
    assert Retention(NO_SAMPLE).decide([det("bee", 0.9), det(cls, conf)]) == "threat"


def test_a_varroa_positive_bee_is_kept() -> None:
    assert Retention(NO_SAMPLE).decide([det("bee", 0.9), det("varroa", 0.6)]) == "varroa"


def test_a_threat_wins_over_varroa() -> None:
    assert Retention(NO_SAMPLE).decide([det("varroa", 0.9), det("hornet", 0.8)]) == "threat"


@pytest.mark.parametrize(
    "objects",
    [[], [det("bee", 0.99)], [det("other_insect", 0.9)], [det("hornet", 0.44)], [det("shb", 0.3)],
     [det("varroa", 0.59)]],
    ids=["empty", "bees", "other insect", "weak hornet", "weak shb", "weak varroa"],
)
def test_nothing_relevant_is_discarded(objects: list[Detection]) -> None:
    assert Retention(NO_SAMPLE).decide(objects) is None


def test_thresholds_come_from_the_rule() -> None:
    rule = RetentionRule(thresholds={"hornet": 0.3, "shb": 0.5, "varroa": 0.6}, sample_rate=0)
    assert Retention(rule).decide([det("hornet", 0.35)]) == "threat"


def test_about_sample_rate_of_the_discarded_frames_is_kept() -> None:
    keep = Retention(RetentionRule(sample_rate=0.05, max_samples_per_day=10_000), random.Random(3))
    kept = sum(keep.decide([]) == "sample" for _ in range(10_000))
    assert 400 < kept < 600


def test_samples_stop_at_the_daily_cap_and_resume_a_day_later() -> None:
    now = [0.0]
    keep = Retention(RetentionRule(sample_rate=1, max_samples_per_day=3), clock=lambda: now[0])
    assert [keep.decide([]) for _ in range(5)] == ["sample", "sample", "sample", None, None]
    now[0] = DAY_S - 1
    assert keep.decide([]) is None
    now[0] = DAY_S
    assert keep.decide([]) == "sample"


def test_the_cap_does_not_hold_back_threats() -> None:
    keep = Retention(RetentionRule(sample_rate=1, max_samples_per_day=0))
    assert keep.decide([det("hornet", 0.9)]) == "threat"


def test_a_rule_without_a_threshold_is_refused() -> None:
    with pytest.raises(ValueError, match="varroa"):
        RetentionRule(thresholds={"hornet": 0.45, "shb": 0.5})
