"""Telemetry message of the messaging contract (docs/05-backend/04-messaging-contract.md).

Hand-written for now; it is replaced by models generated from infra/contracts once those exist (EN-07).
"""

import math
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    field_validator,
    model_validator,
)

from smarthive.contracts.common import Envelope, NonEmpty, schema_field

# The server never converts units, so a known quantity must arrive in its contract unit.
UNITS = {
    "temp_in": "degC",
    "temp_out": "degC",
    "rh_in": "pct_rh",
    "rh_out": "pct_rh",
    "weight": "kg",
    "battery_v": "V",
    "battery_i": "mA",
}
MAX_READINGS = 5000  # readings.idx is a smallint


class Reading(BaseModel):
    model_config = ConfigDict(extra="ignore")  # unknown fields are ignored (minor versions add fields)

    ts: AwareDatetime
    mono_ms: Annotated[StrictInt, Field(ge=0)]  # validated, not stored
    clock_synced: StrictBool
    sensor: NonEmpty
    quantity: NonEmpty  # unknown quantities are accepted and stored
    value: StrictInt | StrictFloat | None
    unit: NonEmpty  # validated, not stored
    quality: Literal["ok", "read_error", "clipped", "stuck", "clock_unsynced"]

    @field_validator("value")
    @classmethod
    def _finite(cls, v: int | float | None) -> float | None:
        if v is None:
            return None
        try:
            f = float(v)
        except OverflowError:
            raise ValueError("value out of range") from None
        if not math.isfinite(f):
            raise ValueError("value must be finite")
        return f

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.value is None and self.quality != "read_error":
            raise ValueError("value may be null only when quality is read_error")
        expected = UNITS.get(self.quantity)
        if expected is not None and self.unit != expected:
            raise ValueError(f"unit for {self.quantity} must be {expected}, got {self.unit}")
        return self


class Telemetry(Envelope):
    schema_: Annotated[str, schema_field("telemetry")]
    readings: Annotated[list[Reading], Field(min_length=1, max_length=MAX_READINGS)]
