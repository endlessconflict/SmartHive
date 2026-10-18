"""Password hashing and tokens. No web framework in here, so it is easy to test."""

import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()  # Argon2id with the library's current recommended parameters
ALGORITHM = "HS256"

# Verified against when the email is unknown, so "no such user" takes as long as "wrong password".
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    role: Literal["beekeeper", "admin"]


class InvalidToken(Exception):
    """Expired, tampered with, signed by someone else, or not an access token."""


def create_access_token(secret: str, user_id: UUID, role: str, minutes: int, now: float | None = None) -> str:
    issued = int(now if now is not None else time.time())
    claims = {"sub": str(user_id), "role": role, "typ": "access", "iat": issued, "exp": issued + minutes * 60}
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def decode_access_token(secret: str, token: str) -> AccessClaims:
    try:
        # algorithms is pinned: a token that names "none" or another algorithm is refused, not trusted
        claims = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require": ["exp", "iat", "sub"]})
        if claims.get("typ") != "access" or claims.get("role") not in ("beekeeper", "admin"):
            raise InvalidToken("not an access token")
        return AccessClaims(UUID(claims["sub"]), claims["role"])
    except (jwt.PyJWTError, ValueError) as e:
        raise InvalidToken(str(e)) from None


def new_refresh_token() -> tuple[str, str]:
    """(token for the cookie, hash for the database). The database never sees the token itself."""
    token = secrets.token_urlsafe(32)
    return token, hash_refresh_token(token)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
