from pathlib import Path

import pytest

from pi_node.main import Config

BASE = 'node_id = "node-0001"\n'
SCALE = """
[scale]
dout_gpio = 5
sck_gpio = 6
offset = 8000
counts_per_kg = 21500.5
"""


def load(tmp_path: Path, text: str) -> Config:
    path = tmp_path / "node.toml"
    path.write_text(text)
    return Config.load(path)


def test_the_scale_is_optional(tmp_path: Path) -> None:
    assert load(tmp_path, BASE).scale is None


def test_the_scale_defaults_to_one_reading_every_five_minutes(tmp_path: Path) -> None:
    scale = load(tmp_path, BASE + SCALE).scale
    assert scale is not None
    assert (scale.dout_gpio, scale.sck_gpio, scale.offset, scale.counts_per_kg) == (5, 6, 8000, 21500.5)
    assert scale.interval_s == 300
    assert scale.chip == "/dev/gpiochip0"


def test_an_uncalibrated_scale_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="counts_per_kg"):
        load(tmp_path, BASE + SCALE.replace("21500.5", "0"))


IMAGES = """
[images]
api_url = "https://gateway.local"
device_token_file = "/etc/smarthive/device_token"
sample_rate = 0.05

[images.thresholds]
hornet = 0.4
"""


def test_without_an_images_section_the_node_handles_no_images(tmp_path: Path) -> None:
    assert load(tmp_path, BASE).images is None


def test_an_images_section_overrides_only_what_it_names(tmp_path: Path) -> None:
    images = load(tmp_path, BASE + IMAGES).images
    assert images is not None
    assert images.frames_dir == Path("/run/smarthive/frames")
    assert images.retention_days == 3
    assert images.rule.sample_rate == 0.05
    assert images.rule.max_samples_per_day == 24
    assert images.rule.thresholds == {"hornet": 0.4, "shb": 0.50, "varroa": 0.60}


def test_a_sample_rate_above_one_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="sample_rate"):
        load(tmp_path, BASE + IMAGES.replace("0.05", "5"))
