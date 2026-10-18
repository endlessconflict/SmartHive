"""Metadata part of an image upload (`meta` in POST /device/v1/images)."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class DetectedObject(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cls: str
    conf: Annotated[float, Field(ge=0, le=1)]
    box: Annotated[list[float], Field(min_length=4, max_length=4)]


class ImageMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    image_id: UUID
    node_id: str
    captured_at: AwareDatetime
    clock_synced: bool
    reason: Literal["threat", "varroa", "periodic", "on_demand"]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    width: Annotated[int, Field(gt=0, le=20000)] | None = None
    height: Annotated[int, Field(gt=0, le=20000)] | None = None
    objects: Annotated[list[DetectedObject], Field(max_length=200)] = []
