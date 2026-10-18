"""Rules: each takes its stored params and returns the conditions that are true now.

Event rules (`once`) name one occurrence; window rules name a standing condition and auto-resolve
only where the catalog says so.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from smarthive.alerts.store import Finding
from smarthive.api.deps import Db

Evaluate = Callable[[Db, dict[str, Any], datetime], Awaitable[list[Finding]]]


MASK_MARGIN = (
    "30 minutes"  # readings this long after a logged management event are left out of rules and ML features
)


@dataclass(frozen=True)
class Rule:
    id: str
    evaluate: Evaluate
    once: bool = False  # key names one occurrence, never reopens
    auto_resolve: bool = False  # alert closes itself when the condition clears


def _threat(cls: str, label: str) -> Evaluate:
    async def evaluate(conn: Db, params: dict[str, Any], now: datetime) -> list[Finding]:
        rows = (
            await conn.execute(
                text(
                    "SELECT episode_id, node_id, hive_id, max_conf, first_seen FROM detection_events "
                    "WHERE type = 'threat_detected' AND cls = :c AND hive_id IS NOT NULL "
                    "AND received_at > CAST(:now AS timestamptz) - interval '1 day'"
                ),
                {"c": cls, "now": now},
            )
        ).all()
        return [
            Finding(
                f"{cls}_detected",
                f"{cls}_detected:{r.hive_id}:{r.episode_id}",
                f"{label} at the entrance",
                {
                    "episode_id": str(r.episode_id),
                    "max_conf": r.max_conf,
                    "first_seen": r.first_seen.isoformat(),
                },
                r.hive_id,
                r.node_id,
            )
            for r in rows
        ]

    return evaluate


async def varroa_high(conn: Db, p: dict[str, Any], now: datetime) -> list[Finding]:
    rows = (
        await conn.execute(
            text(
                "SELECT hive_id, sum(varroa_positive) AS pos, sum(varroa_classified) AS n "
                "FROM vision_summaries WHERE hive_id IS NOT NULL AND window_end > CAST(:now AS timestamptz) - make_interval(hours => :h) "
                "GROUP BY hive_id HAVING sum(varroa_classified) >= :min "
                "AND 100.0 * sum(varroa_positive) / sum(varroa_classified) > :thr"
            ),
            {"now": now, "h": p["hours"], "min": p["min_bees"], "thr": p["threshold_pct"]},
        )
    ).all()
    return [
        Finding(
            "varroa_high",
            f"varroa_high:{r.hive_id}",
            "Varroa index above threshold",
            {
                "index_pct": round(100.0 * r.pos / r.n, 2),
                "bees_classified": int(r.n),
                "threshold_pct": p["threshold_pct"],
            },
            r.hive_id,
        )
        for r in rows
    ]


async def node_offline(conn: Db, p: dict[str, Any], now: datetime) -> list[Finding]:
    rows = (
        await conn.execute(
            text(
                "SELECT n.id, n.last_seen_at, (SELECT hive_id FROM node_assignments a WHERE a.node_id = n.id "
                "AND a.valid @> CAST(:now AS timestamptz)) AS hive_id FROM nodes n WHERE n.last_seen_at IS NOT NULL "
                "AND (n.status = 'offline' OR n.last_seen_at < CAST(:now AS timestamptz) - make_interval(mins => :m))"
            ),
            {"now": now, "m": p["silent_minutes"]},
        )
    ).all()
    return [
        Finding(
            "node_offline",
            f"node_offline:{r.id}",
            f"Node {r.id} is offline",
            {"last_seen_at": r.last_seen_at.isoformat()},
            r.hive_id,
            r.id,
            "critical" if now - r.last_seen_at > timedelta(hours=p["escalate_after_hours"]) else None,
        )
        for r in rows
    ]


async def node_power_low(conn: Db, p: dict[str, Any], now: datetime) -> list[Finding]:
    """Battery below the threshold in every reading of the window, or the Pi's under-voltage flag set in
    at least `uv_snapshots` health snapshots of it. Simulated nodes count: they are how this is demoed."""
    rows = (
        await conn.execute(
            text(
                "WITH low AS ("
                "  SELECT node_id, avg(value) AS volts, 'battery_v' AS why FROM readings "
                "  WHERE quantity = 'battery_v' AND quality = 'ok' "
                "  AND ts > CAST(:now AS timestamptz) - make_interval(mins => :m) AND ts <= CAST(:now AS timestamptz) "
                "  GROUP BY node_id HAVING count(*) >= 2 AND bool_and(value < :v) "
                "  UNION ALL "
                "  SELECT node_id, NULL, 'under_voltage' FROM node_health "
                "  WHERE ts > CAST(:now AS timestamptz) - make_interval(mins => :m) AND ts <= CAST(:now AS timestamptz) "
                "  AND data -> 'throttled' ->> 'under_voltage' = 'true' "
                "  GROUP BY node_id HAVING count(*) >= :uv"
                ") SELECT DISTINCT ON (low.node_id) low.node_id, low.volts, low.why, "
                "(SELECT hive_id FROM node_assignments a WHERE a.node_id = low.node_id "
                "AND a.valid @> CAST(:now AS timestamptz)) AS hive_id FROM low ORDER BY low.node_id, low.why"
            ),
            {"now": now, "m": p["minutes"], "v": p["battery_v_min"], "uv": p["uv_snapshots"]},
        )
    ).all()
    return [
        Finding(
            "node_power_low",
            f"node_power_low:{r.node_id}",
            f"Node {r.node_id} has a weak power supply",
            {"reason": r.why, "battery_v": None if r.volts is None else round(r.volts, 2)},
            r.hive_id,
            r.node_id,
        )
        for r in rows
    ]


def _out_of_range(rule_id: str, label: str) -> Evaluate:
    async def evaluate(conn: Db, p: dict[str, Any], now: datetime) -> list[Finding]:
        # every ok reading of the last `hours` is outside the range, and they span most of that time;
        # hives with a management event running (or just ended) are left alone
        rows = (
            await conn.execute(
                text(
                    "SELECT hive_id, avg(value) AS mean FROM readings WHERE hive_id IS NOT NULL "
                    "AND quantity = :q AND quality = 'ok' AND ts > CAST(:now AS timestamptz) - make_interval(hours => :h) AND ts <= CAST(:now AS timestamptz) "
                    "AND NOT EXISTS (SELECT 1 FROM management_events m WHERE m.hive_id = readings.hive_id "
                    f"AND m.started_at <= CAST(:now AS timestamptz) AND coalesce(m.ended_at, CAST(:now AS timestamptz)) > CAST(:now AS timestamptz) - interval '{MASK_MARGIN}') "
                    "GROUP BY hive_id HAVING bool_and(value < :lo OR value > :hi) "
                    "AND min(ts) <= CAST(:now AS timestamptz) - make_interval(hours => :h) * 0.9"
                ),
                {"q": p["quantity"], "h": p["hours"], "lo": p["low"], "hi": p["high"], "now": now},
            )
        ).all()
        return [
            Finding(
                rule_id,
                f"{rule_id}:{r.hive_id}",
                label,
                {"mean": round(r.mean, 2), "low": p["low"], "high": p["high"], "hours": p["hours"]},
                r.hive_id,
            )
            for r in rows
        ]

    return evaluate


RULES: dict[str, Rule] = {
    r.id: r
    for r in (
        Rule("hornet_detected", _threat("hornet", "Hornet"), once=True),
        Rule("shb_detected", _threat("shb", "Small hive beetle"), once=True),
        Rule("varroa_high", varroa_high),
        Rule("node_offline", node_offline, auto_resolve=True),
        Rule("node_power_low", node_power_low, auto_resolve=True),
        Rule("temp_out_of_range", _out_of_range("temp_out_of_range", "Hive temperature out of range")),
        Rule("rh_out_of_range", _out_of_range("rh_out_of_range", "Hive humidity out of range")),
    )
}
