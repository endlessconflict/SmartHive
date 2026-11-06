"""HX711 load cell amplifier, bit-banged through the GPIO character device (libgpiod), channel A at gain 128.

No kernel driver here, unlike the DHT11, so the timing is ours: SCK held high for more than 60 us powers the
chip down, and Python can be preempted at that moment. A bad conversion is therefore expected now and then,
and one measurement is the median of several.

    python -m pi_node.hx711 --dout 5 --sck 6     # prints raw counts, for the calibration in README.md
"""

import argparse
import statistics
import time
from dataclasses import dataclass
from typing import Literal, Protocol

MAX_RAW = 0x7FFFFF  # the chip reports these two values when the input is out of range
MIN_RAW = -0x800000
READY_TIMEOUT_S = 0.5  # conversions take 100 ms at the 10 samples/s of the usual board
SAMPLES = 9


@dataclass(frozen=True)
class Weight:
    kg: float | None
    quality: Literal["ok", "clipped", "read_error"]


class Pins(Protocol):
    def dout(self) -> bool: ...
    def sck(self, high: bool) -> None: ...


class GpiodPins:
    def __init__(self, chip: str, dout: int, sck: int) -> None:
        import gpiod  # only on the Pi; the tests use fake pins
        from gpiod.line import Direction, Value

        self._active, self._inactive = Value.ACTIVE, Value.INACTIVE
        self._dout, self._sck = dout, sck
        self._lines = gpiod.request_lines(
            chip,
            consumer="smarthive-hx711",
            config={
                dout: gpiod.LineSettings(direction=Direction.INPUT),
                sck: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE),
            },
        )

    def dout(self) -> bool:
        return self._lines.get_value(self._dout) == self._active

    def sck(self, high: bool) -> None:
        self._lines.set_value(self._sck, self._active if high else self._inactive)


def read_raw(pins: Pins, timeout_s: float = READY_TIMEOUT_S) -> int | None:
    """One conversion as a signed 24-bit count, or None if the chip never signals that it is ready."""
    deadline = time.monotonic() + timeout_s
    while pins.dout():  # DOUT goes low when a conversion is ready
        if time.monotonic() > deadline:
            return None
        time.sleep(0.001)
    raw = 0
    for _ in range(24):
        pins.sck(True)
        pins.sck(False)  # DOUT holds until the next rising edge, so SCK stays high as briefly as possible
        raw = raw << 1 | pins.dout()
    pins.sck(True)  # a 25th pulse selects channel A, gain 128 for the next conversion
    pins.sck(False)
    return raw - (1 << 24) if raw & (1 << 23) else raw


def median_raw(pins: Pins, samples: int = SAMPLES, timeout_s: float = READY_TIMEOUT_S) -> int | None:
    """The median of `samples` conversions, or None if fewer than half of them succeeded."""
    values = [v for v in (read_raw(pins, timeout_s) for _ in range(samples)) if v is not None]
    return statistics.median_low(values) if len(values) * 2 >= samples else None


class Hx711:
    def __init__(self, pins: Pins, offset: int, counts_per_kg: float, samples: int = SAMPLES) -> None:
        self.pins = pins
        self.offset = offset  # raw count with nothing on the scale
        self.counts_per_kg = counts_per_kg
        self.samples = samples

    def read(self) -> Weight:
        """Everything on the scale in kg, the hive itself included."""
        raw = median_raw(self.pins, self.samples)
        if raw is None:
            return Weight(None, "read_error")
        kg = (raw - self.offset) / self.counts_per_kg
        return Weight(kg, "clipped" if raw in (MAX_RAW, MIN_RAW) else "ok")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chip", default="/dev/gpiochip0")
    ap.add_argument("--dout", type=int, required=True, help="BCM number of the DOUT line")
    ap.add_argument("--sck", type=int, required=True, help="BCM number of the SCK line")
    args = ap.parse_args()
    print(median_raw(GpiodPins(args.chip, args.dout, args.sck), samples=21))


if __name__ == "__main__":
    main()
