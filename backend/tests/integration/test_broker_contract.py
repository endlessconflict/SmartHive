"""The real broker configuration from infra/ against the messaging contract. Needs Docker, bash and openssl.

Starts Mosquitto with infra/mosquitto/{mosquitto.conf,acl}, issues certificates with infra/pki/gen_certs.sh
and checks who may publish and subscribe where, then runs the ingestor over mutual TLS. If someone edits the
ACL or the certificate script in a way that breaks the contract, this is the test that fails.
"""

import asyncio
import json
import shutil
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import aiomqtt
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from smarthive.config import Settings
from smarthive.ingest import service

REPO = Path(__file__).parents[3]
INFRA = REPO / "infra"
MOSQUITTO_IMAGE = "eclipse-mosquitto:2.0.22"
FIXTURE = (Path(__file__).parents[1] / "fixtures" / "telemetry_valid.json").read_bytes()
NODES = ("node-0001", "node-0002")
SILENCE_S = 1.5  # how long "nothing arrived" is observed for


def _bash() -> str | None:
    git_bash = Path(
        "C:/Program Files/Git/bin/bash.exe"
    )  # on Windows `bash` may be WSL, which cannot see these paths
    if sys.platform == "win32":
        return str(git_bash) if git_bash.exists() else None
    return shutil.which("bash")


pytestmark = pytest.mark.skipif(
    _bash() is None or shutil.which("openssl") is None,
    reason="needs bash and openssl for infra/pki/gen_certs.sh",
)


class Pki:
    def __init__(self, directory: Path) -> None:
        self.dir = directory

    def tls(self, user: str | None) -> aiomqtt.TLSParameters:
        if user is None:  # trusts the CA but presents no certificate
            return aiomqtt.TLSParameters(ca_certs=str(self.dir / "ca.crt"))
        return aiomqtt.TLSParameters(
            ca_certs=str(self.dir / "ca.crt"),
            certfile=str(self.dir / f"{user}.crt"),
            keyfile=str(self.dir / f"{user}.key"),
        )


@pytest.fixture(scope="module")
def pki(tmp_path_factory: pytest.TempPathFactory) -> Pki:
    directory = tmp_path_factory.mktemp("pki")
    bash = _bash()
    assert bash is not None
    # two runs on purpose: adding a device must not invalidate the certificates already issued
    for ids in (["backend", NODES[0]], [NODES[1]]):
        subprocess.run(
            [bash, str(INFRA / "pki" / "gen_certs.sh"), *ids], cwd=directory, check=True, capture_output=True
        )
    for key in directory.glob("*.key"):
        key.chmod(0o644)  # the broker runs as another user inside the container
    return Pki(directory)


@pytest.fixture(scope="module")
def broker(pki: Pki) -> Iterator[tuple[str, int]]:
    container = (
        DockerContainer(MOSQUITTO_IMAGE)
        .with_exposed_ports(8883)
        .with_volume_mapping(str(INFRA / "mosquitto" / "mosquitto.conf"), "/mosquitto/config/mosquitto.conf")
        .with_volume_mapping(str(INFRA / "mosquitto" / "acl"), "/mosquitto/config/acl")
        .with_volume_mapping(str(pki.dir), "/mosquitto/certs")
    )
    with container:
        wait_for_logs(container, "mosquitto version .* running")
        yield container.get_container_host_ip(), int(container.get_exposed_port(8883))


def topic(node: str, suffix: str) -> str:
    return f"smarthive/v1/nodes/{node}/{suffix}"


def connect(broker: tuple[str, int], pki: Pki, user: str | None) -> aiomqtt.Client:
    host, port = broker
    return aiomqtt.Client(host, port, identifier=f"{user}-{uuid.uuid4().hex[:6]}", tls_params=pki.tls(user))


async def received(client: aiomqtt.Client, within: float) -> list[str]:
    topics: list[str] = []

    async def drain() -> None:
        async for message in client.messages:
            topics.append(str(message.topic))

    try:
        await asyncio.wait_for(drain(), timeout=within)
    except TimeoutError:
        pass
    return topics


async def test_node_publishes_on_its_own_topic_and_the_backend_hears_it(
    broker: tuple[str, int], pki: Pki
) -> None:
    async with connect(broker, pki, "backend") as backend, connect(broker, pki, NODES[0]) as node:
        await backend.subscribe("smarthive/v1/nodes/+/#", qos=1)
        for suffix in ("telemetry", "events", "summary", "health", "status", "cmd/ack"):
            await node.publish(topic(NODES[0], suffix), b"{}", qos=1)
        got = await received(backend, SILENCE_S)
    assert sorted(got) == sorted(
        topic(NODES[0], s) for s in ("telemetry", "events", "summary", "health", "status", "cmd/ack")
    )


async def test_a_node_cannot_publish_as_another_node(broker: tuple[str, int], pki: Pki) -> None:
    async with connect(broker, pki, "backend") as backend, connect(broker, pki, NODES[0]) as node:
        await backend.subscribe("smarthive/v1/nodes/+/#", qos=1)
        await node.publish(topic(NODES[1], "telemetry"), b"{}", qos=1)  # someone else's topic
        await node.publish("smarthive/v1/nodes/node-0001/config", b"{}", qos=1)  # server-to-node topic
        await node.publish(topic(NODES[0], "telemetry"), b"{}", qos=1)  # control: this one is allowed
        got = await received(backend, SILENCE_S)
    assert got == [topic(NODES[0], "telemetry")]


async def test_a_node_reads_only_its_own_config_and_commands(broker: tuple[str, int], pki: Pki) -> None:
    async with connect(broker, pki, "backend") as backend, connect(broker, pki, NODES[0]) as node:
        await node.subscribe("smarthive/v1/nodes/+/config", qos=1)
        await node.subscribe("smarthive/v1/nodes/+/cmd", qos=1)
        for target in NODES:
            await backend.publish(topic(target, "config"), b"{}", qos=1)
            await backend.publish(topic(target, "cmd"), b"{}", qos=1)
        got = await received(node, SILENCE_S)
    assert sorted(got) == [topic(NODES[0], "cmd"), topic(NODES[0], "config")]


async def test_a_node_cannot_read_what_other_nodes_send(broker: tuple[str, int], pki: Pki) -> None:
    async with connect(broker, pki, NODES[0]) as spy, connect(broker, pki, NODES[1]) as other:
        await spy.subscribe("smarthive/v1/nodes/+/telemetry", qos=1)
        await other.publish(topic(NODES[1], "telemetry"), b"{}", qos=1)
        assert await received(spy, SILENCE_S) == []


async def test_a_connection_without_a_client_certificate_is_refused(
    broker: tuple[str, int], pki: Pki
) -> None:
    with pytest.raises(aiomqtt.MqttError):
        async with connect(broker, pki, None):
            pass


async def test_the_ingestor_stores_telemetry_over_mutual_tls(
    broker: tuple[str, int], pki: Pki, engine: AsyncEngine, db_url: str
) -> None:
    host, port = broker
    settings = Settings(
        db_url=db_url,
        mqtt_host=host,
        mqtt_port=port,
        mqtt_tls_ca=str(pki.dir / "ca.crt"),
        mqtt_tls_cert=str(pki.dir / "backend.crt"),
        mqtt_tls_key=str(pki.dir / "backend.key"),
        mqtt_client_id=f"test-{uuid.uuid4().hex[:8]}",
    )
    stop = asyncio.Event()
    runner = asyncio.create_task(service.run(settings, stop))
    try:
        async with connect(broker, pki, NODES[0]) as node:
            for _ in range(50):  # the ingestor may not be subscribed yet; a re-sent batch is harmless
                await node.publish(topic(NODES[0], "telemetry"), FIXTURE, qos=1)
                await asyncio.sleep(0.3)
                async with engine.connect() as conn:
                    rows = (await conn.execute(text("SELECT count(*) FROM readings"))).scalar_one()
                if rows == len(json.loads(FIXTURE)["readings"]):
                    break
        assert rows == len(json.loads(FIXTURE)["readings"])
        assert not runner.done()
    finally:
        stop.set()
        await asyncio.wait_for(runner, timeout=10)


async def test_the_ingestor_handles_every_node_topic_through_the_broker(
    broker: tuple[str, int], pki: Pki, engine: AsyncEngine, db_url: str
) -> None:
    host, port = broker
    fixtures = Path(__file__).parents[1] / "fixtures"
    settings = Settings(
        db_url=db_url,
        mqtt_host=host,
        mqtt_port=port,
        mqtt_tls_ca=str(pki.dir / "ca.crt"),
        mqtt_tls_cert=str(pki.dir / "backend.crt"),
        mqtt_tls_key=str(pki.dir / "backend.key"),
        mqtt_client_id=f"test-{uuid.uuid4().hex[:8]}",
    )
    sent = {
        "events": ("event_threat.json", 1, "SELECT count(*) FROM detection_events"),
        "summary": ("summary_valid.json", 1, "SELECT count(*) FROM vision_summaries"),
        "health": ("health_valid.json", 0, "SELECT count(*) FROM node_health"),  # QoS 0, like the node
    }
    stop = asyncio.Event()
    runner = asyncio.create_task(service.run(settings, stop))
    try:
        async with connect(broker, pki, NODES[0]) as node:
            for _ in range(50):
                for suffix, (name, qos, _sql) in sent.items():
                    await node.publish(topic(NODES[0], suffix), (fixtures / name).read_bytes(), qos=qos)
                await node.publish(topic(NODES[0], "status"), b'{"state": "online", "boot_id": "b1"}', qos=1)
                await asyncio.sleep(0.4)
                async with engine.connect() as conn:
                    counts = [(await conn.execute(text(sql))).scalar_one() for _n, _q, sql in sent.values()]
                if counts == [1, 1, 1]:
                    break
        assert counts == [1, 1, 1]  # re-sent copies were deduplicated on the way
        async with engine.connect() as conn:
            status = (
                await conn.execute(text("SELECT status FROM nodes WHERE id = :n"), {"n": NODES[0]})
            ).scalar_one()
        assert status == "online"
        assert not runner.done()
    finally:
        stop.set()
        await asyncio.wait_for(runner, timeout=10)
