"""Stylized-fact tests: docs/04-data/02-hive-telemetry-simulator.md, section 9."""
import json

import numpy as np
import pandas as pd
import pytest

from simulation.telemetry import sim

M = sim.M


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    cfg = sim.merge(sim.DEFAULTS, {"hives": 8, "period": {"start": "2024-01-01", "days": 120},
                                   "events": {"swarm_per_year": 6, "abscond_per_year": 2}})
    out = sim.run(cfg, 7, tmp_path_factory.mktemp("base"))
    t = pd.read_parquet(out / "telemetry.parquet")
    e = pd.read_parquet(out / "events.parquet")
    d = pd.read_parquet(out / "colony_daily.parquet")
    w = pd.read_parquet(out / "weather.parquet")
    params = json.loads((out / "manifest.json").read_text())["hive_params"]
    return cfg, t, e, d, w, params


def healthy_days(t, e, d, params):
    """(hive, date) pairs: strong colony (N > 15k), brood present, probe at brood center, no colony or management event."""
    busy = {(r.hive_id, day) for r in e.itertuples() if not r.type.startswith(("sensor", "node"))
            for day in pd.date_range(r.start.normalize(), r.end.normalize() + pd.Timedelta(days=1)).date}
    ok = d[(d.queen == "present") & (d.B > 2000) & (d.N > 15000)]
    return {(h, day) for h, day in zip(ok.hive_id, ok.date)
            if params[h]["position"] == "brood_center" and (h, day) not in busy}


def per_day(t, keys):
    t = t.assign(date=t.ts.dt.date)
    return t[[(h, day) in keys for h, day in zip(t.hive_id, t.date)]]


def test_1_2_brood_temperature_regulated(base):
    _, t, e, d, _, params = base
    x = per_day(t, healthy_days(t, e, d, params))
    assert len(x) > 1000
    assert x.temp_in_true.between(33.5, 36.5).mean() >= 0.90
    inside = x.groupby(["hive_id", "date"]).temp_in_true.std()
    w = base[4]
    outside = w.groupby(w.ts.dt.date).temp_out.std()
    ratio = inside.values / outside.reindex(inside.index.get_level_values("date")).values
    assert np.median(ratio) < 0.3


def daily_weight(t, hour):
    x = t[(t.ts.dt.hour == int(hour)) & (t.ts.dt.minute == int(round((hour % 1) * 60)))]
    return x.set_index([x.hive_id, x.ts.dt.date]).weight_true


def test_3_4_daily_weight_cycle(base):
    _, t, e, d, w, params = base
    keys = healthy_days(t, e, d, params)
    flow = set(d[d.bloom > 0.6].date)
    rain = w[w.rain_mmh > 0].ts.dt.date.unique()
    days = [k for k in keys if k[1] in flow and k[1] not in set(rain)]
    w7, w9, w12, w1730, w20 = (daily_weight(t, h) for h in (7, 9, 12, 17.5, 20))
    idx = pd.MultiIndex.from_tuples(days)
    assert ((w9.reindex(idx) - w7.reindex(idx)) < 0).mean() >= 0.8, "morning drop"
    assert ((w1730.reindex(idx) - w12.reindex(idx)) > 0).mean() >= 0.7, "afternoon gain"
    w5 = daily_weight(t, 5)
    nxt = pd.MultiIndex.from_tuples([(h, day + pd.Timedelta(days=1)) for h, day in days])
    assert ((w5.reindex(nxt).values - w20.reindex(idx).values) < 0).mean() >= 0.7, "overnight loss"


def test_5_rain_cuts_gain(base):
    _, t, e, d, w, params = base
    wet = set(w[(w.rain_mmh > 0) & w.ts.dt.hour.between(9, 16)].groupby(w.ts.dt.date).size().loc[lambda s: s >= 24].index)
    keys = healthy_days(t, e, d, params)
    flow = set(d[d.bloom > 0.6].date)
    w5 = daily_weight(t, 5)  # 24 h net change; at 18:00 rainwater on the lid would still count as gain
    nxt = w5.copy()
    nxt.index = pd.MultiIndex.from_tuples([(h, day - pd.Timedelta(days=1)) for h, day in w5.index], names=w5.index.names)
    gain = nxt - w5
    g = pd.DataFrame({"gain": gain}).reset_index()
    g.columns = ["hive_id", "date", "gain"]
    g = g[[(h, day) in keys and day in flow for h, day in zip(g.hive_id, g.date)]]
    g["wet"] = g.date.isin(wet)
    per_hive = g.groupby(["hive_id", "wet"]).gain.mean().unstack().dropna()
    assert len(per_hive) >= 2
    assert (per_hive[True] - per_hive[False]).mean() < 0


def test_6_swarm_signature(base):
    _, t, e, *_ = base
    sw = e[e.type == "swarm"]
    assert len(sw) >= 2
    tt = t.set_index(["hive_id", "ts"]).weight_true
    for r in sw.itertuples():
        assert 10 <= r.start.hour < 14
        before = tt.loc[r.hive_id].asof(r.start - pd.Timedelta(minutes=5))
        after = tt.loc[r.hive_id].asof(r.end + pd.Timedelta(minutes=5))
        assert 0.8 <= before - after <= 4.0, (r, before - after)


def test_7_absconding_goes_ambient(base):
    _, t, e, _, w, _ = base
    ab = e[e.type == "absconding"]
    assert len(ab) >= 1
    wo = w.set_index("ts").temp_out
    for r in ab.itertuples():
        x = t[(t.hive_id == r.hive_id) & (t.ts > r.end + pd.Timedelta(hours=6)) & (t.ts < r.end + pd.Timedelta(hours=30))]
        x = x[(x.ts.dt.hour < 6) | (x.ts.dt.hour > 19)]  # night: no solar heating of the box
        assert (x.temp_in_true.values - wo.reindex(x.ts).values).__abs__().mean() < 2.0


def test_8_brood_humidity(base):
    _, t, e, d, _, params = base
    x = per_day(t, healthy_days(t, e, d, params))
    assert x.rh_in_true.between(45, 70).mean() >= 0.8


def test_9_deterministic(tmp_path):
    cfg = sim.merge(sim.DEFAULTS, {"hives": 2, "period": {"days": 10}})
    a = pd.read_parquet(sim.run(cfg, 3, tmp_path / "a") / "telemetry.parquet")
    b = pd.read_parquet(sim.run(cfg, 3, tmp_path / "b") / "telemetry.parquet")
    pd.testing.assert_frame_equal(a, b)


def test_sensor_model_matches_dht11(base):
    _, t, *_ = base
    v = t.temp_in.dropna()
    assert np.allclose(v, v.round()) and v.between(0, 50).all()
    assert t.rh_in.dropna().between(20, 90).all()
    assert set(t.temp_in_q) <= {"ok", "read_error", "clipped", "stuck", "clock_unsynced", "no_data"}
