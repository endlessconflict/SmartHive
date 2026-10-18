"""Vision summary every ten minutes: traffic and the Varroa window."""

from typing import Annotated, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator

from smarthive.contracts.common import Envelope, schema_field

Count = Annotated[int, Field(ge=0, le=2_000_000_000)]


class Window(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start: AwareDatetime
    end: AwareDatetime
    clock_synced: StrictBool = True  # validated, not stored

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end <= self.start:
            raise ValueError("window must end after it starts")
        return self


class Varroa(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bees_classified: Count
    positive: Count

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.positive > self.bees_classified:
            raise ValueError("more Varroa-positive bees than bees classified")
        return self


class Summary(Envelope):
    schema_: Annotated[str, schema_field("summary")]
    window: Window
    frames_analyzed: Count
    counts: Annotated[dict[str, Count], Field(max_length=64)]
    varroa: Varroa
