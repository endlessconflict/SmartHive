"""Demo history for the anomaly warnings (US17): days of normal readings, then a change in the last hours.

    docker compose run --rm api demo-anomaly --node sim-0001 --quantity temp_in   # entrypoint: smarthive

The anomaly rule compares a hive with its own previous days, so it needs history a live fake node cannot
produce in a demo. This writes it straight into `readings`, for a simulated node assigned to a hive only.
The node's readings in that period are replaced, so the command can be run again.
"""

import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smarthive.alerts.anomaly import MODEL

STEP = timedelta(minutes=5)
# (sensor, mean, sd); a brood nest, and a scale like the simulator's HX711
NORMAL = {
    "temp_in": ("dht11-0", 35.0, 0.4),
    "rh_in": ("dht11-0", 58.0, 2.0),
    "weight": ("hx711-0", 41.0, 0.03),
}
# inside the out-of-range thresholds (32-37 degC, 40-85 %): only the anomaly rule sees them. Weight in kg/h
DEFAULT_SHIFT = {"temp_in": 1.3, "rh_in": -14.0, "weight": -0.8}


def history(
    now: datetime, quantity: str, shift: float, days: float, hours: float, rng: random.Random
) -> list[tuple[datetime, str, str, float]]:
    """(ts, quantity, sensor, value) every 5 minutes; `shift` added to `quantity` in the last `hours`."""
    start = now - timedelta(days=days)
    change_at = now - timedelta(hours=hours)
    rows = []
    ts = start
    while ts <= now:
        hours_in = max(0.0, (ts - change_at) / timedelta(hours=1))
        for q, (sensor, mean, sd) in NORMAL.items():
            value = rng.gauss(mean, sd)
            if q == quantity and ts >= change_at:
                value += shift * hours_in if q == "weight" else shift
            rows.append((ts, q, sensor, round(value, 2 if q == "weight" else 1)))
        ts += STEP
    return rows


async def write_history(
    engine: AsyncEngine,
    node: str,
    quantity: str,
    shift: float | None = None,
    days: float = 3,
    hours: float = 4,
    now: datetime | None = None,
    seed: int | None = None,
    real_node: bool = False,
) -> dict[str, Any]:
    """`real_node`: also for a node without the sim- prefix. Its real readings in the period are replaced."""
    now = now or datetime.now(UTC)
    shift = DEFAULT_SHIFT[quantity] if shift is None else shift
    async with engine.begin() as c:
        row = (
            await c.execute(
                text(
                    "SELECT n.is_simulated, a.hive_id FROM nodes n LEFT JOIN node_assignments a "
                    "ON a.node_id = n.id AND a.valid @> CAST(:now AS timestamptz) WHERE n.id = :n"
                ),
                {"n": node, "now": now},
            )
        ).first()
        if row is None:
            raise SystemExit(f"{node} does not exist: register it in Setup first")
        if not row.is_simulated and not real_node:
            raise SystemExit(
                f"{node} is not a simulated node (sim-...): its last {days:g} days of readings would be "
                "replaced by demo data. Add --real-node if that is what you want"
            )
        if row.hive_id is None:
            raise SystemExit(f"{node} is not attached to a hive: attach it in Setup first")
        await c.execute(
            text(
                "DELETE FROM readings WHERE node_id = :n AND ts >= CAST(:start AS timestamptz) "
                "AND ts <= CAST(:now AS timestamptz)"
            ),
            {"n": node, "start": now - timedelta(days=days), "now": now},
        )
        # windows the rule found in the replaced readings would no longer match them
        await c.execute(
            text(
                "DELETE FROM anomalies WHERE hive_id = :h AND model = :m "
                "AND period && tstzrange(CAST(:start AS timestamptz), NULL)"
            ),
            {"h": row.hive_id, "m": MODEL, "start": now - timedelta(days=days)},
        )
        rows = history(now, quantity, shift, days, hours, random.Random(seed))
        msg = {ts: uuid.uuid4() for ts, *_ in rows}  # one message per sample, as a node sends them
        params = [
            {
                "ts": ts,
                "n": node,
                "h": row.hive_id,
                "q": q,
                "v": v,
                "s": sensor,
                "m": msg[ts],
                "i": ["temp_in", "rh_in", "weight"].index(q),
            }
            for ts, q, sensor, v in rows
        ]
        await c.execute(
            text(
                "INSERT INTO readings (ts, node_id, hive_id, quantity, value, quality, sensor, clock_synced, "
                "msg_id, idx) VALUES (:ts, :n, :h, :q, :v, 'ok', :s, true, :m, :i)"
            ),
            params,
        )
    return {"hive_id": row.hive_id, "readings": len(params), "quantity": quantity, "shift": shift}
