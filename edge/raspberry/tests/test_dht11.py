from pathlib import Path

import pytest

from pi_node.dht11 import Dht11, Measurement, SensorNotFound, find_device


def fake_iio(root: Path, name: str = "dht11", temp: str = "35000", rh: str = "58000") -> Path:
    # Windows does not allow ":" in directory names.
    dev = root / "iio-device0"
    dev.mkdir()
    (dev / "name").write_text(name + "\n")
    (dev / "in_temp_input").write_text(temp + "\n")
    (dev / "in_humidityrelative_input").write_text(rh + "\n")
    return dev


def test_reads_milli_units(tmp_path: Path) -> None:
    dev = fake_iio(tmp_path)
    assert find_device(tmp_path) == dev
    assert Dht11(dev).read() == Measurement(35.0, 58.0)


def test_failed_reads_give_none(tmp_path: Path) -> None:
    dev = fake_iio(tmp_path)
    (dev / "in_temp_input").unlink()  # the driver answers EIO; a missing file is the same OSError family
    assert Dht11(dev, attempts=2, retry_delay_s=0).read() is None


def test_missing_overlay(tmp_path: Path) -> None:
    fake_iio(tmp_path, name="mcp3008")
    with pytest.raises(SensorNotFound):
        find_device(tmp_path)
