"""Opaque cursors for list endpoints: `limit` and `cursor`, newest-stable keyset order."""

import base64
import binascii
from typing import Annotated
from uuid import UUID

from fastapi import Query

from smarthive.api.errors import Problem


def decode_uuid_cursor(cursor: str | None) -> UUID | None:
    """For lists ordered by a uuid primary key: the cursor is the last id of the previous page."""
    value = decode_cursor(cursor)
    try:
        return None if value is None else UUID(value)
    except ValueError:
        raise Problem(400, "Invalid cursor") from None


Limit = Annotated[int, Query(ge=1, le=200, description="Page size")]
Cursor = Annotated[str | None, Query(description="Opaque value from `next_cursor` of the previous page")]


def encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> str | None:
    if cursor is None:
        return None
    try:
        # validate=True: characters outside the alphabet are an error, not silently dropped
        return base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True).decode()
    except (binascii.Error, UnicodeDecodeError):
        raise Problem(400, "Invalid cursor") from None
