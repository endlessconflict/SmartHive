"""Retained `status` message. The last will cannot carry an envelope, so there is no msg_id here."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Status(BaseModel):
    model_config = ConfigDict(extra="ignore")

    state: Literal["online", "offline"]
    boot_id: str | None = None
    reason: str | None = None
