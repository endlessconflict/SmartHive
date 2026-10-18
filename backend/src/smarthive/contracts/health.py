"""Health snapshot every minute. The whole document is stored as received; only the envelope is checked."""

from typing import Annotated

from pydantic import StrictBool

from smarthive.contracts.common import Envelope, schema_field


class Health(Envelope):
    schema_: Annotated[str, schema_field("health")]
    clock_synced: StrictBool | None = None  # when false, `sent_at` is not trusted as the snapshot time
