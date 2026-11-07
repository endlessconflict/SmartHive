"""US08: frames kept by the node's real filter, uploaded with the node's own request body, stored by the API."""

import io
import json
import random
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from pi_node.fake_camera import FakeCamera
from pi_node.frames import FrameFilter
from pi_node.image_upload import multipart
from pi_node.outbox import Outbox
from pi_node.retention import Retention, RetentionRule
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.api.app import create_app
from smarthive.config import Settings
from tests.integration.test_alerts import setup_hive
from tests.integration.test_api_auth import SECRET
from tests.integration.test_api_images import give_token, user_auth

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(engine: AsyncEngine, tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(jwt_secret=SECRET, image_dir=str(tmp_path / "server"))
    transport = httpx.ASGITransport(app=create_app(settings, engine), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.test") as c:
        yield c


async def test_kept_frames_go_up_as_the_node_sends_them(
    client: httpx.AsyncClient, engine: AsyncEngine, tmp_path: Path
) -> None:
    owner, hive, node = await setup_hive(engine)
    headers = await give_token(engine, node)
    box = Outbox(tmp_path / "outbox.db")
    try:
        camera = FakeCamera(tmp_path / "frames", random.Random(5), frame_kb=60)
        filt = FrameFilter(
            node, tmp_path / "frames", tmp_path / "images", box, Retention(RetentionRule(sample_rate=1))
        )
        camera.shoot("hornet")
        camera.shoot("bees")  # kept only because sample_rate=1
        filt.process()
        rows = box.pending_images()
        assert [r.reason for r in rows] == ["threat", "sample"]

        for row in rows:
            content_type, body = multipart(row.meta, row.path.read_bytes(), f"{row.image_id}.jpg")
            r = await client.post(
                "/device/v1/images", content=body, headers={**headers, "Content-Type": content_type}
            )
            assert r.status_code == 201, r.text
            again = await client.post(
                "/device/v1/images", content=body, headers={**headers, "Content-Type": content_type}
            )
            assert again.status_code == 200  # a retry after a lost response
    finally:
        box.close()

    gallery = (await client.get(f"/api/v1/hives/{hive}/images", headers=user_auth(owner))).json()["items"]
    assert sorted(i["reason"] for i in gallery) == ["sample", "threat"]
    threat = next(i for i in gallery if i["reason"] == "threat")
    assert threat["id"] == json.loads(rows[0].meta)["image_id"]
    assert [o["cls"] for o in threat["objects"]].count("hornet") == 1

    thumb = await client.get(f"/api/v1/images/{threat['id']}/file?w=160", headers=user_auth(owner))
    assert thumb.status_code == 200
    assert Image.open(io.BytesIO(thumb.content)).format == "JPEG"  # the padded fake frame is a real JPEG

    async with engine.connect() as c:
        keep = dict(
            (
                await c.execute(
                    text("SELECT reason, expires_at - captured_at FROM images WHERE node_id = :n"),
                    {"n": node},
                )
            ).all()
        )
    assert keep == {"threat": timedelta(days=365), "sample": timedelta(days=30)}
