"""Site weather from Open-Meteo, stored per apiary. The worker refreshes it daily."""

import asyncio
import json
import logging
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

log = logging.getLogger("smarthive.weather")

URL = "https://api.open-meteo.com/v1/forecast"
SOURCE = "open-meteo-forecast"  # the forecast endpoint also serves `past_days` of analysed history
_HOURLY = {
    "temperature_2m": "temp_c",
    "relative_humidity_2m": "rh_pct",
    "precipitation": "precip_mm",
    "wind_speed_10m": "wind_ms",
    "shortwave_radiation": "radiation_wm2",
}
Fetcher = Callable[[float, float], Awaitable[dict[str, Any]]]

_UPSERT = text(
    "INSERT INTO weather (ts, apiary_id, temp_c, rh_pct, precip_mm, wind_ms, radiation_wm2, source) "
    "VALUES (:ts, :apiary, :temp_c, :rh_pct, :precip_mm, :wind_ms, :radiation_wm2, :source) "
    "ON CONFLICT (apiary_id, ts, source) DO UPDATE SET temp_c = EXCLUDED.temp_c, rh_pct = EXCLUDED.rh_pct, "
    "precip_mm = EXCLUDED.precip_mm, wind_ms = EXCLUDED.wind_ms, radiation_wm2 = EXCLUDED.radiation_wm2"
)


def _get(lat: float, lon: float) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(_HOURLY),
            "wind_speed_unit": "ms",
            "past_days": 7,
            "forecast_days": 3,
            "timezone": "UTC",
        }
    )
    with urllib.request.urlopen(f"{URL}?{query}", timeout=30) as response:  # noqa: S310  (fixed https URL)
        doc: dict[str, Any] = json.load(response)
    return doc


async def fetch(lat: float, lon: float) -> dict[str, Any]:
    return await asyncio.to_thread(_get, lat, lon)


def rows(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """One dict per hour, with our column names. Open-Meteo answers in UTC when asked to."""
    hourly = doc["hourly"]
    return [
        {"ts": datetime.fromisoformat(t).replace(tzinfo=UTC)}
        | {ours: hourly[theirs][i] for theirs, ours in _HOURLY.items()}
        for i, t in enumerate(hourly["time"])
    ]


async def refresh_all(engine: AsyncEngine, fetcher: Fetcher = fetch) -> int:
    """Store weather for every apiary that has coordinates. One failing site does not stop the others."""
    async with engine.connect() as conn:
        sites = (
            await conn.execute(
                text("SELECT id, lat, lon FROM apiaries WHERE lat IS NOT NULL AND lon IS NOT NULL")
            )
        ).all()
    stored = 0
    for site in sites:
        try:
            hours = rows(await fetcher(site.lat, site.lon))
        except Exception:
            log.exception("weather_fetch_failed", extra={"fields": {"apiary_id": str(site.id)}})
            continue
        async with engine.begin() as conn:
            for h in hours:
                await conn.execute(_UPSERT, {**h, "apiary": site.id, "source": SOURCE})
        stored += len(hours)
    return stored
