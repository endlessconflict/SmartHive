from pi_node.hx711 import MAX_RAW, Hx711, Weight, median_raw, read_raw


class FakePins:
    """An HX711 that serves the given raw counts, then stays busy (DOUT high) like a chip that is gone."""

    def __init__(self, *counts: int) -> None:
        self.counts = list(counts)
        self.bits: list[int] = []
        self.pulses: list[int] = []
        self.pulse = 0
        self.level = False

    def dout(self) -> bool:
        if self.bits:
            return bool(self.bits[-1])
        return not self.counts

    def sck(self, high: bool) -> None:
        if high and not self.level:  # data shifts out on the rising edge
            if not self.pulse and self.counts:
                word = self.counts.pop(0) & 0xFFFFFF
                self.bits = [(word >> i) & 1 for i in range(24)]  # the next bit to read is last
            elif self.pulse:
                self.bits.pop()
            self.pulse += 1
            if self.pulse == 25:
                self.pulses.append(self.pulse)
                self.pulse = 0
        self.level = high


def test_counts_are_signed_24_bit() -> None:
    assert read_raw(FakePins(1234)) == 1234
    assert read_raw(FakePins(-1234)) == -1234
    assert read_raw(FakePins(MAX_RAW)) == MAX_RAW
    assert read_raw(FakePins(-0x800000)) == -0x800000


def test_each_conversion_takes_25_pulses_so_the_next_one_stays_at_gain_128() -> None:
    pins = FakePins(1, 2)
    assert read_raw(pins) == 1
    assert read_raw(pins) == 2
    assert pins.pulses == [25, 25]


def test_a_chip_that_never_gets_ready_gives_none() -> None:
    assert read_raw(FakePins(), timeout_s=0) is None


def test_the_median_ignores_a_bad_conversion() -> None:
    assert median_raw(FakePins(100, 100, -8000000, 101, 99), samples=5) == 100


def test_too_few_conversions_is_a_failure() -> None:
    assert median_raw(FakePins(100), samples=5, timeout_s=0) is None
    assert median_raw(FakePins(100, 101, 102), samples=5, timeout_s=0) == 101


def test_read_applies_the_calibration() -> None:
    scale = Hx711(FakePins(*[53000] * 3), offset=8000, counts_per_kg=1000.0, samples=3)
    assert scale.read() == Weight(45.0, "ok")


def test_read_reports_a_saturated_input_as_clipped() -> None:
    scale = Hx711(FakePins(*[MAX_RAW] * 3), offset=0, counts_per_kg=1000.0, samples=3)
    assert scale.read().quality == "clipped"
