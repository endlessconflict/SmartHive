"""Event message: detections and node-side alarms."""

from typing import Annotated, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from smarthive.contracts.common import Envelope, NonEmpty, schema_field


class EventBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # threat_detected, varroa_high, sensor_fault, storage_low, dropped_data; a new type is stored as is
    type: NonEmpty
    episode_id: UUID | None = None  # absent for events that are not part of an episode
    cls: str | None = None
    first_seen: AwareDatetime | None = None
    last_seen: AwareDatetime | None = None
    max_conf: Annotated[float, Field(ge=0, le=1)] | None = None
    frames_positive: Annotated[int, Field(ge=0, le=32767)] | None = None
    frames_window: Annotated[int, Field(ge=0, le=32767)] | None = None
    image_id: UUID | None = None  # may point at an image that has not arrived yet
    models: dict[str, str] | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.first_seen and self.last_seen and self.last_seen < self.first_seen:
            raise ValueError("last_seen is before first_seen")
        return self


class Event(Envelope):
    schema_: Annotated[str, schema_field("event")]
    event: EventBody
