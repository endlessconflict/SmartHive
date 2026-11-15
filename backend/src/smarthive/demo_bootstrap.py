"""A ready-to-show apiary for the live demo: one account, five hives with their nodes, a week of history.

    docker compose run --rm bootstrap          # in demo/; also runs by itself on `docker compose up`

What it writes, all through plain SQL on the tables the API reads, so the dashboard cannot tell it from a week
of real operation:

* an administrator, an apiary and five hives, each with a simulated node attached since eight days ago,
* readings every ten minutes for seven days: brood-nest temperature and humidity with a daily swing, and a
  hive weight that gains in the daytime and slips a little at night,
* hourly weather, inspections, a feeding and a treatment in the beekeeper's log,
* on hive 3, a humidity drop in the last hours, so the anomaly warning (US17) is on screen from the start.

The node ids and weights match `demo/simulator/sim.py`, which carries on from where the history stops. It
does nothing when the account exists, so restarting the stack keeps what the demo has collected.
"""

import json
import math
import os
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.alerts.engine import evaluate_all
from smarthive.api.security import hash_password

STEP = timedelta(minutes=10)
DAYS = 7
# (hive name, hive type, boxes, node, weight now in kg, kg gained per day on average)
HIVES = [
    ("Hive 1 - Queen Anne", "Langstroth", 2, "sim-0001", 41.0, 1.6),
    ("Hive 2 - Riverside", "Langstroth", 2, "sim-0002", 38.5, 0.9),
    ("Hive 3 - Orchard", "Langstroth", 3, "sim-0003", 44.2, 1.2),
    ("Hive 4 - Old Oak", "Warre", 2, "sim-0004", 36.8, 0.5),
    ("Hive 5 - Nursery", "Langstroth", 1, "sim-0005", 39.9, 1.4),
]
ANOMALY_HIVE = 2  # index in HIVES: humidity falls 14 points in the last four hours


def readings(
    now: datetime,
    node: str,
    hive: uuid.UUID,
    kg_now: float,
    kg_day: float,
    humidity_drop: bool,
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Samples every ten minutes, ending at `now` with `kg_now`."""
    start = now - timedelta(days=DAYS)
    n = int(DAYS * 24 * 60 / 10)
    rows = []

    # weight: forage gain between 07:00 and 16:00 (local, UTC-5), a small loss overnight, scaled to kg_day
    def gain(ts: datetime) -> float:
        h = (ts.hour + ts.minute / 60 - 5) % 24
        return (1.0 if 7 <= h < 16 else -0.18) * (1 / 6)  # per ten minutes, unscaled

    day_gain = sum(gain(start + i * STEP) for i in range(144))
    scale = kg_day / day_gain if day_gain else 0
    weights, w = [], kg_now
    for i in range(n, -1, -1):  # walk back from now so the series ends at kg_now
        ts = start + i * STEP
        weights.append(w)
        w -= gain(ts) * scale
    weights.reverse()
    for i in range(n + 1):
        ts = start + i * STEP
        h = (ts.hour + ts.minute / 60 - 5) % 24
        temp = 35.0 + 0.45 * math.sin((h - 9) / 24 * 2 * math.pi) + rng.gauss(0, 0.2)
        rh = 58.0 - 3.0 * math.sin((h - 9) / 24 * 2 * math.pi) + rng.gauss(0, 0.9)
        if humidity_drop and ts >= now - timedelta(hours=4):
            rh -= 14.0
        for idx, (q, sensor, v) in enumerate(
            [
                ("temp_in", "dht11-0", temp),
                ("rh_in", "dht11-0", rh),
                ("weight", "hx711-0", weights[i] + rng.gauss(0, 0.02)),
            ]
        ):
            rows.append(
                {
                    "ts": ts,
                    "n": node,
                    "h": hive,
                    "q": q,
                    "v": round(v, 2),
                    "s": sensor,
                    "m": uuid.uuid4(),
                    "i": idx,
                }
            )
    return rows


def weather(now: datetime, rng: random.Random) -> list[dict[str, Any]]:
    out = []
    for hours in range(24 * (DAYS + 1)):
        ts = (now - timedelta(hours=hours)).replace(minute=0, second=0, microsecond=0)
        h = (ts.hour - 5) % 24
        sun = max(0.0, math.sin((h - 6) / 12 * math.pi))
        out.append(
            {
                "ts": ts,
                "temp": round(25 + 5 * sun + rng.gauss(0, 0.4), 1),
                "rh": round(88 - 22 * sun + rng.gauss(0, 2), 1),
                "rain": round(max(0.0, rng.gauss(0.2, 0.5)) if rng.random() < 0.12 else 0.0, 1),
                "wind": round(abs(rng.gauss(1.8, 0.7)), 1),
                "rad": round(850 * sun * rng.uniform(0.7, 1.0)),
            }
        )
    return out


async def run(engine: AsyncEngine, email: str, password: str, name: str, now: datetime | None = None) -> bool:
    """Returns False, writing nothing, when the account already exists."""
    now = (now or datetime.now(UTC)).replace(second=0, microsecond=0)
    rng = random.Random(2026)
    async with engine.begin() as c:
        if (await c.execute(text("SELECT 1 FROM users WHERE email = :e"), {"e": email})).first():
            return False
        user, apiary = uuid.uuid4(), uuid.uuid4()
        await c.execute(
            text(
                "INSERT INTO users (id, email, display_name, password_hash, role) VALUES (:i, :e, :n, :p, 'admin')"
            ),
            {"i": user, "e": email, "n": name, "p": hash_password(password)},
        )
        await c.execute(
            text(
                "INSERT INTO apiaries (id, owner_id, name, lat, lon, timezone) VALUES (:i, :u, :n, 8.43, -80.0, 'America/Panama')"
            ),
            {"i": apiary, "u": user, "n": "El Cielo Apiary"},
        )
        await c.execute(
            text(
                "INSERT INTO weather (ts, apiary_id, temp_c, rh_pct, precip_mm, wind_ms, radiation_wm2, source) "
                "VALUES (:ts, :a, :temp, :rh, :rain, :wind, :rad, 'demo-synthetic') ON CONFLICT DO NOTHING"
            ),
            [{**w, "a": apiary} for w in weather(now, rng)],
        )
        # Demo timing: a scenario lasts minutes, so the windows are shortened (2 h and 300 bees in production)
        await c.execute(
            text("UPDATE alert_rules SET params = params || '{\"min_bees\": 100}' WHERE id = 'varroa_high'")
        )
        await c.execute(
            text(
                "UPDATE alert_rules SET params = params || '{\"hours\": 0.04}' WHERE id = 'temp_out_of_range'"
            )
        )
        hive_ids = []
        for i, (hive_name, kind, boxes, node, kg_now, kg_day) in enumerate(HIVES):
            hive = uuid.uuid4()
            hive_ids.append(hive)
            await c.execute(
                text(
                    "INSERT INTO hives (id, apiary_id, name, hive_type, boxes, installed_on) "
                    "VALUES (:i, :a, :n, :t, :b, :d)"
                ),
                {
                    "i": hive,
                    "a": apiary,
                    "n": hive_name,
                    "t": kind,
                    "b": boxes,
                    "d": (now - timedelta(days=200)).date(),
                },
            )
            await c.execute(
                text("INSERT INTO nodes (id, is_simulated) VALUES (:id, true) ON CONFLICT (id) DO NOTHING"),
                {"id": node},
            )
            await c.execute(
                text(
                    "INSERT INTO node_assignments (node_id, hive_id, valid) VALUES (:n, :h, tstzrange(:s, NULL))"
                ),
                {"n": node, "h": hive, "s": now - timedelta(days=DAYS + 1)},
            )
            rows = readings(now, node, hive, kg_now, kg_day, i == ANOMALY_HIVE, rng)
            for k in range(0, len(rows), 5000):
                await c.execute(
                    text(
                        "INSERT INTO readings (ts, node_id, hive_id, quantity, value, quality, sensor, clock_synced, msg_id, idx) "
                        "VALUES (:ts, :n, :h, :q, :v, 'ok', :s, true, :m, :i)"
                    ),
                    rows[k : k + 5000],
                )
        log = [
            (
                0,
                "inspection",
                now - timedelta(days=5, hours=3),
                {"notes": "Strong brood pattern, queen seen", "frames_of_bees": 9},
            ),
            (1, "feeding", now - timedelta(days=3, hours=6), {"notes": "2 L of 1:1 syrup"}),
            (3, "treatment", now - timedelta(days=2, hours=4), {"notes": "Oxalic acid, drip method"}),
            (4, "super_added", now - timedelta(days=4, hours=2), {"notes": "Second honey super"}),
        ]
        for idx, kind, at, data in log:
            await c.execute(
                text(
                    "INSERT INTO management_events (id, hive_id, type, started_at, ended_at, data, created_by) "
                    "VALUES (:i, :h, :t, :s, :e, CAST(:d AS jsonb), :u)"
                ),
                {
                    "i": uuid.uuid4(),
                    "h": hive_ids[idx],
                    "t": kind,
                    "s": at,
                    "e": at + timedelta(minutes=40),
                    "d": json.dumps(data),
                    "u": user,
                },
            )
    await evaluate_all(engine)  # the anomaly of hive 3 is on screen at once, not a minute later
    return True


def credentials() -> tuple[str, str, str]:
    return (
        os.environ.get("SMARTHIVE_DEMO_EMAIL", "demo@smarthive.dev"),
        os.environ.get("SMARTHIVE_DEMO_PASSWORD", "SmartHive-Demo-2026"),
        os.environ.get("SMARTHIVE_DEMO_NAME", "Demo Beekeeper"),
    )
