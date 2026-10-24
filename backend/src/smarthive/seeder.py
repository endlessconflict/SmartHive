"""Test-data seeder: publishes contract-valid node messages over MQTT (issue #22).

It plays the part of an edge node, so a fresh stack can be filled without hardware and the whole
path (broker, ingest, database, alert engine, API, WebSocket) can be checked by hand. The payload
builders are pure functions; `tests/unit/test_seeder.py` validates every one against the contract models.
"""

import asyncio
import json
import random
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import aiomqtt

from smarthive.config import Settings
from smarthive.ingest.service import tls_parameters

SCENARIOS = ("normal", "hornet", "varroa", "low-battery", "offline")
TOPIC = "smarthive/v1/nodes/{node}/{kind}"
READING_STEP = timedelta(minutes=5)  # backdated readings, so time-window alert rules can fire at once


def _iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _envelope(schema: str, node: str, boot: str, now: datetime) -> dict[str, Any]:
    return {
        "schema": f"smarthive.{schema}/1.0",
        "msg_id": str(uuid.uuid4()),
        "node_id": node,
        "boot_id": boot,
        "sent_at": _iso(now),
    }


def telemetry(
    node: str, boot: str, now: datetime, scenario: str, rng: random.Random, count: int = 3
) -> dict[str, Any]:
    """`count` readings per quantity, `READING_STEP` apart, newest at `now`."""
    battery = 9.8 if scenario == "low-battery" else 12.4
    readings = []
    for i in range(count):
        ts = _iso(now - READING_STEP * i)
        mono = 1_000_000 + int((now - READING_STEP * i).timestamp()) % 1_000_000 * 1000
        for sensor, quantity, value, unit in (
            ("dht11-0", "temp_in", round(rng.gauss(35, 0.4), 1), "degC"),
            ("dht11-0", "rh_in", round(rng.gauss(58, 1.5), 1), "pct_rh"),
            ("dht22-1", "temp_out", round(rng.gauss(27, 1.0), 1), "degC"),
            ("hx711-0", "weight", round(rng.gauss(41, 0.05), 2), "kg"),
            ("ina219-0", "battery_v", round(rng.gauss(battery, 0.03), 2), "V"),
        ):
            readings.append(
                {"ts": ts, "mono_ms": mono, "clock_synced": True, "sensor": sensor, "quantity": quantity,
                 "value": value, "unit": unit, "quality": "ok"}
            )  # fmt: skip
    return {**_envelope("telemetry", node, boot, now), "readings": readings}


def health(node: str, boot: str, now: datetime, scenario: str, rng: random.Random) -> dict[str, Any]:
    low = scenario == "low-battery"
    return {
        **_envelope("health", node, boot, now),
        "uptime_s": 8772,
        "soc_temp_c": round(rng.gauss(52, 1.5), 1),
        "throttled": {"under_voltage_now": low, "under_voltage_since_boot": low},
        "cpu_load": round(rng.uniform(0.2, 0.6), 2),
        "mem_used_mb": 310,
        "disk_free_mb": 24100,
        "outbox_pending": 0,
        "images_pending": 0,
        "dropped_total": 0,
        "clock_synced": True,
        "ntp_offset_ms": 3.1,
        "config_version": 1,
        "versions": {"software": "seeder", "stage1": "none"},
    }


def summary(node: str, boot: str, now: datetime, scenario: str, rng: random.Random) -> dict[str, Any]:
    classified = 1800
    positive = 400 if scenario == "varroa" else rng.randint(10, 40)  # about 22 % against 1-2 %
    end = now.replace(second=0, microsecond=0)
    return {
        **_envelope("summary", node, boot, now),
        "window": {"start": _iso(end - timedelta(minutes=10)), "end": _iso(end), "clock_synced": True},
        "frames_analyzed": 300,
        "counts": {"bee": 2900, "hornet": 0, "shb": 0, "other_insect": rng.randint(20, 50)},
        "varroa": {"bees_classified": classified, "positive": positive},
        "latency_ms_p95": {"stage1": 600, "total": 1400},
    }


def threat_event(node: str, boot: str, now: datetime) -> dict[str, Any]:
    first = now - timedelta(seconds=30)
    return {
        **_envelope("event", node, boot, now),
        "event": {
            "type": "threat_detected",
            "episode_id": str(uuid.uuid4()),
            "cls": "hornet",
            "first_seen": _iso(first),
            "last_seen": _iso(now - timedelta(seconds=10)),
            "clock_synced": True,
            "max_conf": 0.88,
            "frames_positive": 6,
            "frames_window": 10,
            "models": {"stage1": "seeder", "stage2": "seeder"},
        },
    }


def messages(
    node: str, boot: str, now: datetime, scenario: str, rng: random.Random
) -> list[tuple[str, Any, bool]]:
    """(kind, payload, retain) for one round of the scenario."""
    if scenario == "offline":
        return [("status", {"state": "offline", "boot_id": boot, "reason": "seeder"}, True)]
    builders: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("telemetry", lambda: telemetry(node, boot, now, scenario, rng)),
        ("health", lambda: health(node, boot, now, scenario, rng)),
        ("summary", lambda: summary(node, boot, now, scenario, rng)),
    ]
    if scenario == "hornet":
        builders.append(("events", lambda: threat_event(node, boot, now)))
    return [(kind, build(), False) for kind, build in builders]


async def publish(
    settings: Settings, node: str, scenario: str, rounds: int, interval_s: float, seed: int | None
) -> int:
    """Connect as `node` (the broker reads the user from the cert CN); returns the message count."""
    rng = random.Random(seed)
    boot = str(uuid.uuid4())
    sent = 0
    async with aiomqtt.Client(
        settings.mqtt_host,
        settings.mqtt_port,
        username=settings.mqtt_username,
        password=settings.mqtt_password,
        identifier=f"seeder-{node}-{boot[:8]}",
        tls_params=tls_parameters(settings),
    ) as client:
        if scenario != "offline":
            online = {"state": "online", "boot_id": boot}
            await client.publish(
                TOPIC.format(node=node, kind="status"), json.dumps(online), qos=1, retain=True
            )
        for n in range(rounds):
            if n:
                await asyncio.sleep(interval_s)
            for kind, payload, retain in messages(node, boot, datetime.now(UTC), scenario, rng):
                await client.publish(
                    TOPIC.format(node=node, kind=kind), json.dumps(payload), qos=1, retain=retain
                )
                sent += 1
    return sent
