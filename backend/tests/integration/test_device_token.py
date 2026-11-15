"""A node asks for its image-upload token over MQTT: the answer works on the API, and replaces the old one."""

import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.ingest import device_token
from smarthive.ingest.service import give_token
from tests.integration.test_alerts import setup_hive
from tests.integration.test_api_images import client, upload  # noqa: F401  (the fixture)

pytestmark = pytest.mark.integration


def test_only_the_request_topic_of_a_node_is_a_request() -> None:
    assert device_token.requester("smarthive/v1/nodes/node-0001/token/req") == "node-0001"
    assert device_token.requester("smarthive/v1/nodes/node-0001/token") is None
    assert device_token.requester("smarthive/v1/nodes/node-0001/telemetry") is None
    assert device_token.requester("smarthive/v1/nodes/+/token/req") is None
    assert device_token.answer_topic("node-0001") == "smarthive/v1/nodes/node-0001/token"


async def test_the_token_a_node_asked_for_uploads_and_the_old_one_stops(
    client: httpx.AsyncClient,  # noqa: F811
    engine: AsyncEngine,
) -> None:
    _, _, node = await setup_hive(engine)
    old = json.loads(await device_token.issue(engine, node))["token"]
    answer = await give_token(engine, node)
    assert answer is not None
    new = json.loads(answer)["token"]
    assert new != old and len(new) >= 40

    assert (await upload(client, {"Authorization": f"Bearer {new}"}, node)).status_code == 201
    assert (await upload(client, {"Authorization": f"Bearer {old}"}, node)).status_code == 401


async def test_a_node_nobody_registered_yet_is_added(engine: AsyncEngine) -> None:
    node = f"sim-{uuid4().hex[:6]}"
    await device_token.issue(engine, node)
    async with engine.connect() as c:
        row = (
            await c.execute(
                text("SELECT is_simulated, device_token_hash <> '' AS has FROM nodes WHERE id = :n"),
                {"n": node},
            )
        ).one()
    assert row.is_simulated is True and row.has is True
