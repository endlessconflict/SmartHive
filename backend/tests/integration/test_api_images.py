"""Device upload (token, hash, idempotency, limits) and the gallery with its ownership scoping."""

import hashlib
import io
import json
from collections.abc import AsyncIterator, Awaitable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.api.app import create_app
from smarthive.api.security import create_access_token
from smarthive.config import Settings
from tests.integration.test_alerts import setup_hive
from tests.integration.test_api_auth import SECRET, add_user

pytestmark = pytest.mark.integration

JPEG = b"\xff\xd8\xff\xe0" + b"fake-jpeg-body" * 20


@pytest.fixture
async def client(engine: AsyncEngine, tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(jwt_secret=SECRET, image_dir=str(tmp_path), image_max_bytes=10_000)
    transport = httpx.ASGITransport(app=create_app(settings, engine), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as c:
        yield c


def user_auth(user_id: UUID, role: str = "beekeeper") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(SECRET, user_id, role, 15)}"}


async def give_token(engine: AsyncEngine, node: str) -> dict[str, str]:
    token = uuid4().hex
    from smarthive.api.security import hash_refresh_token

    async with engine.begin() as c:
        await c.execute(
            text("UPDATE nodes SET device_token_hash = :h WHERE id = :n"),
            {"h": hash_refresh_token(token), "n": node},
        )
    return {"Authorization": f"Bearer {token}"}


def upload(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    node: str,
    data: bytes = JPEG,
    image_id: UUID | None = None,
    when: datetime | None = None,
    reason: str = "threat",
    sha: str | None = None,
    content_type: str = "image/jpeg",
) -> Awaitable[httpx.Response]:
    meta = {
        "image_id": str(image_id or uuid4()),
        "node_id": node,
        "captured_at": (when or datetime.now(UTC)).isoformat(),
        "clock_synced": True,
        "reason": reason,
        "sha256": sha or hashlib.sha256(data).hexdigest(),
        "width": 640,
        "height": 480,
        "objects": [{"cls": "hornet", "conf": 0.8, "box": [1, 2, 3, 4]}],
    }
    return client.post(
        "/device/v1/images",
        headers=headers,
        data={"meta": json.dumps(meta)},
        files={"file": ("x.jpg", data, content_type)},
    )


async def test_upload_stores_the_file_and_resolves_the_hive(
    client: httpx.AsyncClient, engine: AsyncEngine, tmp_path: Path
) -> None:
    owner, hive, node = await setup_hive(engine)
    headers = await give_token(engine, node)
    image_id = uuid4()

    r = await upload(client, headers, node, image_id=image_id)
    assert r.status_code == 201
    digest = hashlib.sha256(JPEG).hexdigest()
    assert (tmp_path / digest[:2] / digest[2:4] / f"{digest}.jpg").read_bytes() == JPEG

    g = await client.get(f"/api/v1/images/{image_id}", headers=user_auth(owner))
    assert (
        g.status_code == 200
        and g.json()["hive_id"] == str(hive)
        and g.json()["objects"][0]["cls"] == "hornet"
    )
    f = await client.get(f"/api/v1/images/{image_id}/file", headers=user_auth(owner))
    assert f.status_code == 200 and f.content == JPEG and f.headers["content-type"] == "image/jpeg"

    async with engine.connect() as c:
        expires = (
            await c.execute(
                text("SELECT expires_at - captured_at FROM images WHERE id = :i"), {"i": image_id}
            )
        ).scalar()
    assert expires == timedelta(days=365)


async def test_retries_are_idempotent_and_a_different_hash_conflicts(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    _, _, node = await setup_hive(engine)
    headers = await give_token(engine, node)
    image_id = uuid4()
    assert (await upload(client, headers, node, image_id=image_id)).status_code == 201
    assert (await upload(client, headers, node, image_id=image_id)).status_code == 200
    other = b"\xff\xd8\xff" + b"other"
    assert (await upload(client, headers, node, data=other, image_id=image_id)).status_code == 409


async def test_rejections(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    _, _, node = await setup_hive(engine)
    _, _, other_node = await setup_hive(engine)
    headers = await give_token(engine, node)

    assert (await upload(client, {}, node)).status_code == 401
    assert (await upload(client, {"Authorization": "Bearer nope"}, node)).status_code == 401
    assert (await upload(client, headers, other_node)).status_code == 403  # token of another node
    assert (await upload(client, headers, node, sha="0" * 64)).status_code == 422
    assert (await upload(client, headers, node, reason="selfie")).status_code == 422
    assert (await upload(client, headers, node, content_type="image/png")).status_code == 415
    assert (await upload(client, headers, node, data=b"GIF89a-not-a-jpeg")).status_code == 415
    assert (await upload(client, headers, node, data=b"\xff\xd8\xff" + b"x" * 20_000)).status_code == 413
    async with engine.connect() as c:
        assert (
            await c.execute(text("SELECT count(*) FROM images WHERE node_id = :n"), {"n": node})
        ).scalar() == 0


async def test_gallery_is_scoped_filtered_and_paged(client: httpx.AsyncClient, engine: AsyncEngine) -> None:
    owner, hive, node = await setup_hive(engine)
    bob = await add_user(engine, f"bob-{uuid4().hex[:6]}@example.com")
    admin = await add_user(engine, f"adm-{uuid4().hex[:6]}@example.com", "admin")
    headers = await give_token(engine, node)
    now = datetime.now(UTC)
    ids = []
    for i in range(3):
        image_id = uuid4()
        ids.append(str(image_id))
        data = JPEG + bytes([i])
        reason = "periodic" if i == 0 else "threat"
        assert (
            await upload(client, headers, node, data, image_id, now - timedelta(hours=3 - i), reason)
        ).status_code == 201

    url = f"/api/v1/hives/{hive}/images"
    listing = (await client.get(url, headers=user_auth(owner))).json()
    assert [i["id"] for i in listing["items"]] == ids[::-1]  # newest first
    assert [
        i["id"]
        for i in (await client.get(url, params={"reason": "periodic"}, headers=user_auth(owner))).json()[
            "items"
        ]
    ] == [ids[0]]
    window = {"from": (now - timedelta(minutes=150)).isoformat()}
    assert len((await client.get(url, params=window, headers=user_auth(owner))).json()["items"]) == 2

    first = (await client.get(url, params={"limit": 2}, headers=user_auth(owner))).json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    rest = (
        await client.get(url, params={"limit": 2, "cursor": first["next_cursor"]}, headers=user_auth(owner))
    ).json()
    assert [i["id"] for i in first["items"] + rest["items"]] == ids[::-1] and rest["next_cursor"] is None

    latest = await client.get(f"{url}/latest", headers=user_auth(owner))
    assert latest.json()["id"] == ids[2]

    for path in (url, f"{url}/latest", f"/api/v1/images/{ids[0]}", f"/api/v1/images/{ids[0]}/file"):
        assert (await client.get(path, headers=user_auth(bob))).status_code == 404
        assert (await client.get(path, headers=user_auth(admin, "admin"))).status_code == 200
        assert (await client.get(path)).status_code == 401


async def test_a_file_removed_from_the_volume_is_a_404(
    client: httpx.AsyncClient, engine: AsyncEngine, tmp_path: Path
) -> None:
    owner, _, node = await setup_hive(engine)
    headers = await give_token(engine, node)
    image_id = uuid4()
    await upload(client, headers, node, image_id=image_id)
    for f in tmp_path.rglob("*.jpg"):
        f.unlink()
    assert (await client.get(f"/api/v1/images/{image_id}/file", headers=user_auth(owner))).status_code == 404


def real_jpeg(width: int = 1000, height: int = 500) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 120, 20)).save(buf, "JPEG")
    return buf.getvalue()


async def test_thumbnail_is_resized_cached_and_validated(
    client: httpx.AsyncClient, engine: AsyncEngine, tmp_path: Path
) -> None:
    owner, _, node = await setup_hive(engine)
    headers = await give_token(engine, node)
    image_id = uuid4()
    assert (await upload(client, headers, node, data=real_jpeg(), image_id=image_id)).status_code == 201

    r = await client.get(f"/api/v1/images/{image_id}/file?w=320", headers=user_auth(owner))
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(r.content)).size == (320, 160)
    assert len(list((tmp_path / "thumbs" / "320").glob("*.jpg"))) == 1

    again = await client.get(f"/api/v1/images/{image_id}/file?w=320", headers=user_auth(owner))
    assert again.content == r.content
    assert (
        await client.get(f"/api/v1/images/{image_id}/file?w=123", headers=user_auth(owner))
    ).status_code == 422
    # not a decodable JPEG (the fake bytes pass the upload check) -> 422, not 500
    bad = uuid4()
    await upload(client, headers, node, image_id=bad)
    assert (await client.get(f"/api/v1/images/{bad}/file?w=160", headers=user_auth(owner))).status_code == 422
