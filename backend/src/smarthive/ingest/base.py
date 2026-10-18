"""What every message handler provides, and what the pipeline gets back."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncConnection


class Rejected(Exception):
    """The message is not valid for its topic. Nothing is stored."""

    def __init__(self, reason: str, errors: list[dict[str, str]] | None = None, msg_id: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.errors = errors or []
        self.msg_id = msg_id


@dataclass(frozen=True)
class Stored:
    """What a handler wrote. `notify` is sent through LISTEN/NOTIFY when the transaction commits."""

    msg_id: str | None
    items: int  # rows the message carried: readings in a batch, 1 for an event
    inserted: int  # rows that were new; 0 for a message that was delivered twice
    notify: dict[str, Any] | None = None

    @property
    def duplicates(self) -> int:
        return self.items - self.inserted


@dataclass(frozen=True)
class Handler:
    """One topic suffix of the contract. A new message type is one of these, registered in handlers/."""

    kind: str  # topic suffix: telemetry, events, summary, health, status
    parse: Callable[[str, dict[str, Any]], Any]  # (node id from the topic, JSON object) -> validated message
    store: Callable[[AsyncConnection, Any], Awaitable[Stored]]
    # What a message proves about the node. "online": a live signal (health is QoS 0 and never queued).
    # "seen": the node spoke, but a queued message can be delivered late. "none": the message is the status.
    liveness: Literal["online", "seen", "none"] = "seen"


@dataclass(frozen=True)
class Result:
    kind: str
    node_id: str
    stored: Stored
