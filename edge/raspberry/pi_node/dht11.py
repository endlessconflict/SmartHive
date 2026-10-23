"""DHT11 through the kernel IIO driver (`dtoverlay=dht11,gpiopin=4` in /boot/firmware/config.txt).

The kernel does the microsecond timing, so no Python GPIO library is needed. The driver exposes
`in_temp_input` (milli-degC) and `in_humidityrelative_input` (milli-%RH); a failed read raises OSError.
"""

import time
from dataclasses import dataclass
from pathlib import Path

IIO_ROOT = Path("/sys/bus/iio/devices")


@dataclass(frozen=True)
class Measurement:
    temp_c: float
    rh_pct: float


class SensorNotFound(RuntimeError):
    pass


def find_device(root: Path = IIO_ROOT) -> Path:
    for dev in sorted(root.glob("iio:device*")):
        try:
            if (dev / "name").read_text().strip().startswith("dht11"):
                return dev
        except OSError:
            continue
    raise SensorNotFound(f"no dht11 device under {root}; is the dht11 overlay enabled?")


class Dht11:
    def __init__(self, device: Path | None = None, attempts: int = 3, retry_delay_s: float = 2.1) -> None:
        self.device = device or find_device()
        self.attempts = attempts
        self.retry_delay_s = retry_delay_s  # the driver caches a reading for 2 s

    def _read_milli(self, name: str) -> float:
        return int((self.device / name).read_text()) / 1000

    def read(self) -> Measurement | None:
        """One measurement, or None if every attempt failed (timeouts and checksum errors are common)."""
        for i in range(self.attempts):
            if i:
                time.sleep(self.retry_delay_s)
            try:
                return Measurement(self._read_milli("in_temp_input"), self._read_milli("in_humidityrelative_input"))
            except (OSError, ValueError):
                continue
        return None
