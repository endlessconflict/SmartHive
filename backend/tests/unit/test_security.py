import time
from uuid import uuid4

import jwt
import pytest

from smarthive.api.ratelimit import FailureLimiter
from smarthive.api.security import (
    InvalidToken,
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)

SECRET = "x" * 40


def test_a_password_verifies_only_against_its_own_hash() -> None:
    h = hash_password("correct horse battery")
    assert h.startswith("$argon2id$")
    assert verify_password("correct horse battery", h)
    assert not verify_password("wrong", h)


def test_an_unknown_user_never_verifies_even_with_the_dummy_password() -> None:
    assert not verify_password("anything", None)
    assert not verify_password("not-a-real-password", None)


def test_a_garbage_hash_is_a_failed_login_not_a_crash() -> None:
    assert not verify_password("x", "not a hash")


def test_an_access_token_round_trips() -> None:
    user = uuid4()
    claims = decode_access_token(SECRET, create_access_token(SECRET, user, "admin", 15))
    assert (claims.user_id, claims.role) == (user, "admin")


def test_an_expired_token_is_refused() -> None:
    token = create_access_token(SECRET, uuid4(), "admin", 15, now=time.time() - 16 * 60)
    with pytest.raises(InvalidToken):
        decode_access_token(SECRET, token)


def test_a_token_signed_with_another_secret_is_refused() -> None:
    with pytest.raises(InvalidToken):
        decode_access_token(SECRET, create_access_token("y" * 40, uuid4(), "admin", 15))


def test_a_tampered_token_is_refused() -> None:
    head, body, sig = create_access_token(SECRET, uuid4(), "beekeeper", 15).split(".")
    with pytest.raises(InvalidToken):
        decode_access_token(SECRET, f"{head}.{body[:-2]}xx.{sig}")


def test_an_unsigned_token_is_refused() -> None:
    forged = jwt.encode(
        {"sub": str(uuid4()), "role": "admin", "typ": "access", "iat": 1, "exp": 4102444800},
        None,
        algorithm="none",
    )
    with pytest.raises(InvalidToken):
        decode_access_token(SECRET, forged)


@pytest.mark.parametrize("claims", [{"typ": "refresh"}, {"role": "root"}, {"sub": "not-a-uuid"}])
def test_a_token_with_the_wrong_claims_is_refused(claims: dict[str, str]) -> None:
    base = {
        "sub": str(uuid4()),
        "role": "admin",
        "typ": "access",
        "iat": int(time.time()),
        "exp": int(time.time()) + 60,
    }
    with pytest.raises(InvalidToken):
        decode_access_token(SECRET, jwt.encode({**base, **claims}, SECRET, algorithm="HS256"))


def test_a_refresh_token_is_stored_as_its_hash() -> None:
    token, digest = new_refresh_token()
    assert digest == hash_refresh_token(token) and token not in digest and len(token) >= 40
    assert new_refresh_token()[0] != token


def test_the_limiter_blocks_after_the_allowed_failures_and_frees_after_the_window() -> None:
    now = [100.0]
    limiter = FailureLimiter(3, 60, clock=lambda: now[0])
    for _ in range(3):
        assert not limiter.blocked("1.2.3.4")
        limiter.fail("1.2.3.4")
    assert limiter.blocked("1.2.3.4") and not limiter.blocked("5.6.7.8")
    assert 1 <= limiter.retry_after("1.2.3.4") <= 61
    now[0] += 61
    assert not limiter.blocked("1.2.3.4")


def test_a_success_clears_the_failures() -> None:
    limiter = FailureLimiter(2, 60)
    limiter.fail("a")
    limiter.reset("a")
    limiter.fail("a")
    assert not limiter.blocked("a")


@pytest.mark.parametrize("cursor", ["!!!", "a b", "@@@@"])
def test_a_cursor_with_foreign_characters_is_rejected(cursor: str) -> None:
    from smarthive.api.errors import Problem
    from smarthive.api.pagination import decode_cursor

    with pytest.raises(Problem):
        decode_cursor(cursor)


def test_a_cursor_round_trips_and_a_non_uuid_cursor_is_rejected_for_uuid_lists() -> None:
    from smarthive.api.errors import Problem
    from smarthive.api.pagination import decode_cursor, decode_uuid_cursor, encode_cursor

    assert decode_cursor(encode_cursor("hello")) == "hello" and decode_cursor(None) is None
    one = uuid4()
    assert decode_uuid_cursor(encode_cursor(str(one))) == one
    with pytest.raises(Problem):
        decode_uuid_cursor(encode_cursor("not-a-uuid"))
