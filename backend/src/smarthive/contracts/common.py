"""Pieces shared by the messaging-contract models (docs/05-backend/04-messaging-contract.md)."""

from typing import Annotated, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

NonEmpty = Annotated[str, Field(min_length=1)]


def schema_field(kind: str) -> object:
    """`smarthive.<kind>/1.x`: minor versions only add optional fields, so any 1.x is accepted."""
    return Field(alias="schema", pattern=rf"^smarthive\.{kind}/1\.\d+$")


class Envelope(BaseModel):
    """Fields every node-to-server message starts with (the `schema` field is declared by each subclass)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)  # unknown fields are ignored

    msg_id: UUID
    node_id: NonEmpty
    boot_id: NonEmpty  # validated, not stored
    sent_at: AwareDatetime

    def expect_node(self, node_id: str) -> Self:
        if self.node_id != node_id:
            raise NodeMismatch(self.msg_id)
        return self


class NodeMismatch(ValueError):
    """The node id in the payload differs from the one in the topic (and so from the certificate)."""

    def __init__(self, msg_id: UUID) -> None:
        super().__init__("node_id does not match the topic")
        self.msg_id = msg_id
