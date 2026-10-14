"""Hive telemetry simulator. Design: docs/04-data/02-hive-telemetry-simulator.md

    python -m simulation.telemetry.sim simulation/telemetry/scenarios/panama_baseline.yaml --seed 42

Writes data/sim/<name>-s<seed>/{telemetry,events,colony_daily,weather}.parquet + manifest.json.
Internal step is 1 minute. Everything random comes from one seeded generator per hive,
so the same scenario + seed always gives the same files.
"""
import argparse
import copy
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.signal import lfilter

VERSION = "1.0.0"
M = 1440  # minutes per day

DEFAULTS = {
    "name": "default",
    "site": {"lat": 8.98, "lon": -79.52, "utc_offset_h": -5},  # Panama: no DST
    "period": {"start": "2024-01-01", "days": 365},
    "output_step_min": 5,
    "hives": 5,
    "climate": {  # Panama-like stochastic weather; replace with Open-Meteo history for the real apiary
        "dry_months": [1, 2, 3, 4, 12],
        "t_mean": {"dry": 27.5, "wet": 26.5}, "t_amp": {"dry": 4.5, "wet": 3.0},
        "rh_mean": {"dry": 72, "wet": 85}, "p_wet_day": {"dry": 0.12, "wet": 0.65},
    },
    # Nectar availability: floor + [center "MM-DD", width_days, height] bumps.
    # Assumption to confirm with the client (EL-10): main flow in the dry season, weak flow mid rainy season.
    "bloom_base": 0.15,
    "bloom": [["02-10", 110, 0.85], ["07-20", 40, 0.3]],
    "colony": {
        "N0": [15000, 40000], "forager_frac": [0.20, 0.35], "peak_out": [0.5, 0.8],
        "trip_min": [30, 50], "load_mg": [20, 35], "lay_max": [1000, 2000],
        "tare_kg": [18, 24], "S0_kg": [5, 15], "T_set": [34.3, 35.5], "RH_set": [50, 65],
        "tau_T_min": [30, 90], "tau_RH_min": [30, 120],
    },
    "probe": {"positions": {"brood_center": 0.7, "brood_edge": 0.2, "super": 0.1},
              "gamma": {"brood_center": [0.01, 0.05], "brood_edge": [0.10, 0.30], "super": [0.30, 0.60]},
              "b_rh": {"brood_center": [0.02, 0.10], "brood_edge": [0.2, 0.4], "super": [0.4, 0.7]}},
    "events": {"swarm_per_year": 0.6, "abscond_per_year": 0.15, "queen_loss_per_year": 0.2,
               "robbing_per_year": 0.3, "inspection_every_days": [7, 21], "harvest": True, "supers": True, "feed_below_kg": 2.0},
    "sensor": {"model": "dht11", "read_fail_p": 0.04, "stuck_per_year": 2, "dropout_per_week": 1.0,
               "hx711": {"res_g": 10, "noise_g": 30, "temp_coeff_g_per_c": [5, 30], "gain_err": 0.02,
                         "creep_g_per_week": [0, 40], "spike_per_day": 0.5}},
    "node": {"power": "mains", "outage_per_week": 0.5, "outage_median_h": 3,
             "battery_wh": [47, 66], "draw_w": {"day": 3.5, "night": 1.8}, "swap_hour": 9,
             "ntp_slow_p": 0.1},
}
# Sensor ranges and resolution (datasheets). Presets let us price a better sensor in the simulator.
SENSORS = {
    "dht11": {"t": (0, 50, 1.0, 2.0, 0.3), "rh": (20, 90, 1.0, 5.0, 1.0)},  # (lo, hi, resolution, max bias, noise sd)
    "sht31": {"t": (-40, 125, 0.01, 0.3, 0.05), "rh": (0, 100, 0.01, 2.0, 0.3)},
    "bme280": {"t": (-40, 85, 0.01, 1.0, 0.1), "rh": (0, 100, 0.01, 3.0, 0.5)},
}
M_BEE = 1e-4  # kg, one worker
HONEY_PER_SWARMER = 35e-6  # kg each swarming bee carries
WATER_LOSS = 0.5  # share of nectar mass lost when it ripens into honey


def merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def u(rng, r):
    return float(rng.uniform(*r)) if isinstance(r, (list, tuple)) else float(r)


def solar_elevation(ts_utc, lat, lon):
    # ponytail: no equation of time (±16 min); fine for a foraging-hours model
    doy = ts_utc.dayofyear.values
    hour = ts_utc.hour.values + ts_utc.minute.values / 60
    decl = np.radians(23.44) * np.sin(2 * np.pi * (284 + doy) / 365)
    ha = np.radians(15 * (hour + lon / 15 - 12))
    la = np.radians(lat)
    return np.degrees(np.arcsin(np.sin(la) * np.sin(decl) + np.cos(la) * np.cos(decl) * np.cos(ha)))


def weather(cfg, idx, rng):
    """Per-minute site weather shared by all hives. idx is local time (naive)."""
    c, days = cfg["climate"], len(idx) // M
    day_idx = idx[::M]
    dry = np.isin(day_idx.month, c["dry_months"])
    pick = lambda key: np.where(dry, c[key]["dry"], c[key]["wet"])
    t_mean = pick("t_mean") + lfilter([1], [1, -0.7], rng.normal(0, 0.6, days))  # AR(1) day-to-day drift
    t_amp = np.clip(pick("t_amp") + rng.normal(0, 0.7, days), 1.0, None)
    wet = np.zeros(days, bool)
    for d in range(days):  # two-state Markov chain, wet days cluster
        p = pick("p_wet_day")[d]
        wet[d] = rng.random() < (min(0.9, p + 0.2) if d and wet[d - 1] else p)
    h = (np.arange(len(idx)) % M) / 60
    # Daily shape: minimum at 06:00, maximum at 14:00, continuous
    shape = np.where((h >= 6) & (h < 14), -np.cos(np.pi * (h - 6) / 8), np.cos(np.pi * ((h - 14) % 24) / 16))
    T = np.repeat(t_mean, M) + np.repeat(t_amp, M) * shape
    rain = np.zeros(len(idx))
    for d in np.flatnonzero(wet):  # afternoon convective rain, sometimes a second shower
        for _ in range(1 + (rng.random() < 0.3)):
            s = d * M + int(rng.uniform(11, 18) * 60)
            rain[s:s + int(rng.uniform(20, 180))] = rng.uniform(1, 15)  # mm/h
    cool = lfilter([0.02], [1, -0.98], (rain > 0).astype(float))  # 0..1, decays ~1 h after rain
    T = T - 3.0 * np.clip(cool * 5, 0, 1)
    rh = np.repeat(pick("rh_mean"), M) - 3.5 * (T - np.repeat(t_mean, M))
    rh = np.clip(np.where(rain > 0, 96, rh) + 10 * np.clip(cool * 5, 0, 1), 35, 100)
    wind = np.repeat(rng.lognormal(np.log(2.5), 0.4, days), M) * (1 + 0.5 * np.clip(shape, 0, None))
    elev = solar_elevation(pd.DatetimeIndex(idx - pd.Timedelta(hours=cfg["site"]["utc_offset_h"])),
                           cfg["site"]["lat"], cfg["site"]["lon"])
    cloud = np.repeat(np.where(wet, 0.5, 0.85), M) * np.where(rain > 0, 0.3, 1)
    rad = np.clip(1000 * np.sin(np.radians(elev)), 0, None) * cloud
    return pd.DataFrame({"temp_out": T, "rh_out": rh, "rain_mmh": rain, "wind_ms": wind,
                         "radiation_wm2": rad, "sun_elev": elev, "wet": np.clip(cool * 5, 0, 1)}, index=idx)


def bloom_curve(cfg, idx):
    doy = idx[::M].dayofyear.values
    f = np.full(len(doy), float(cfg["bloom_base"]))
    for center, width, height in cfg["bloom"]:
        c = pd.Timestamp(f"2001-{center}").dayofyear
        dist = np.minimum(abs(doy - c), 365 - abs(doy - c))
        f += height * np.exp(-0.5 * (dist / (width / 2)) ** 2)
    return np.clip(f, 0, 1)


def schedule(cfg, days, bloom, rng):
    """Daily Bernoulli draws for colony events. Feasibility (queen, strength) is checked at run time."""
    e, ev = cfg["events"], {}
    flow_w = bloom / max(bloom.mean(), 1e-6)
    for d in range(days):
        if rng.random() < e["swarm_per_year"] / 365 * flow_w[d]:
            ev.setdefault(d, []).append("swarm")
        if rng.random() < e["abscond_per_year"] / 365:
            ev.setdefault(d, []).append("absconding")
        if rng.random() < e["queen_loss_per_year"] / 365:
            ev.setdefault(d, []).append("queen_loss")
        if rng.random() < e["robbing_per_year"] / 365 * (2 - flow_w[d].clip(0, 2)):
            ev.setdefault(d, []).append("robbing")
    nxt = int(u(rng, e["inspection_every_days"]))
    while nxt < days:
        ev.setdefault(nxt, []).append("inspection")
        nxt += int(u(rng, e["inspection_every_days"]))
    return ev


def simulate_hive(cfg, hive_id, idx, wx, bloom, rng):
    c, days = cfg["colony"], len(idx) // M
    pos = rng.choice(list(cfg["probe"]["positions"]), p=list(cfg["probe"]["positions"].values()))
    p = {k: u(rng, v) for k, v in c.items()}
    p.update(position=pos, gamma=u(rng, cfg["probe"]["gamma"][pos]), b_rh=u(rng, cfg["probe"]["b_rh"][pos]),
             delay_on=rng.uniform(20, 60), delay_off=rng.uniform(20, 60), a_rh=rng.uniform(3, 10))
    ev_days = schedule(cfg, days, bloom, rng)
    k_ripen = 1 / (24 * 60)
    N, S, P, supers, cap = p["N0"], p["S0_kg"], 0.0, 0, 14.0
    queen, queen_back = "present", -1
    laid = [p["lay_max"] * 0.5] * 21
    robbing_left, dead = 0, False
    cols = {k: np.zeros(len(idx)) for k in ("weight", "T_target", "RH_target", "traffic", "n_out")}
    daily, events = [], []
    T_out, RH_out, rain = wx.temp_out.values, wx.rh_out.values, wx.rain_mmh.values
    sun, rad, wind, wet = wx.sun_elev.values, wx.radiation_wm2.values, wx.wind_ms.values, wx.wet.values
    rainwater = lfilter([1 / 60], [1, -0.995], np.clip(rain, 0, 5) * 0.06)  # kg on the lid, dries slowly

    def log(kind, s, e, **kw):
        events.append({"hive_id": hive_id, "type": kind, "start": idx[min(s, len(idx) - 1)],
                       "end": idx[min(e, len(idx) - 1)], "params": json.dumps(kw)})

    for d in range(days):
        sl = slice(d * M, (d + 1) * M)
        m = np.arange(M)
        todays = ev_days.get(d, [])
        # Colony (daily step)
        if queen == "virgin" and d >= queen_back:
            queen = "present" if rng.random() < 0.9 else "absent"
        lay = 0.0 if dead or queen != "present" else p["lay_max"] * (0.3 + 0.7 * bloom[d]) * (1.0 if S > 1 else 0.3)
        laid.append(lay)
        B_prev, B = B if d else sum(laid[-22:-1]), sum(laid[-21:])
        N_prev = N
        death = 1 / 30 + (0.03 if S < 0.2 else 0)  # starvation
        N = 0.0 if dead else max(0.0, N + 0.85 * laid[-22] - N * death)
        # Within the day (1-minute step)
        daylight = (sun[sl] > 5)
        on = np.argmax(daylight) + p["delay_on"]
        off = M - np.argmax(daylight[::-1]) - p["delay_off"]
        x = np.clip((m - on) / max(off - on, 1), 0, 1)
        g = np.sin(np.pi * x) ** 1.5
        fly = (rain[sl] < 0.5) * (1 - 0.7 * wet[sl]) * np.clip(1.5 - wind[sl] / 8, 0, 1) * np.clip((T_out[sl] - 12) / 6, 0, 1)
        fly *= np.where(T_out[sl] > 36, 0.6, 1.0) * np.clip(0.4 + rad[sl] / 500, 0, 1)  # heat, heavy cloud
        Nm = np.linspace(N_prev, N, M)  # smooth daily update, no step at midnight
        dS = np.zeros(M)
        w_extra = np.zeros(M)
        t_extra = np.zeros(M)
        if not dead and "swarm" in todays and queen == "present" and N > 20000 and bloom[d] > 0.3:
            s0, dur = int(rng.uniform(10, 14) * 60), int(rng.uniform(10, 25))
            frac = min(rng.uniform(0.4, 0.6), 20000 / N)  # primary swarms rarely exceed ~20k bees
            ramp = np.clip((m - s0) / dur, 0, 1) * frac * N
            Nm -= ramp
            dS -= np.diff(ramp, prepend=0) * HONEY_PER_SWARMER
            N *= 1 - frac
            queen, queen_back = "virgin", d + int(rng.uniform(10, 16))
            log("swarm", d * M + s0, d * M + s0 + dur, frac=round(frac, 3), kg=round(frac * Nm[0] * (M_BEE + HONEY_PER_SWARMER), 2))
        if not dead and "absconding" in todays and N > 1000:
            s0, dur = int(rng.uniform(9, 14) * 60), int(rng.uniform(15, 40))
            ramp = np.clip((m - s0) / dur, 0, 1) * N
            Nm -= ramp
            dS -= np.diff(ramp, prepend=0) * HONEY_PER_SWARMER
            log("absconding", d * M + s0, d * M + s0 + dur, bees=int(N))
            dead, N = True, 0.0
        if not dead and "queen_loss" in todays and queen == "present":
            queen = "absent"
            log("queen_loss", d * M + 12 * 60, d * M + 12 * 60)
        if not dead and "robbing" in todays and robbing_left == 0:
            robbing_left = int(rng.uniform(2, 6))
            log("robbing", d * M + 13 * 60, (d + robbing_left) * M + 17 * 60, days=robbing_left)
        rob_today = robbing_left > 0
        if rob_today:
            robbing_left -= 1
            win = (m >= 13 * 60) & (m < 17 * 60)
            dS[win] -= min(S, rng.uniform(0.2, 1.5)) / win.sum()
        out_frac = p["peak_out"] * g * fly * (0.3 + 0.7 * bloom[d]) * (not dead)
        n_out = p["forager_frac"] * Nm * out_frac
        returns = n_out / p["trip_min"]
        intake = returns * p["load_mg"] * 1e-6 * bloom[d] * (S < cap)  # fly and bloom already shape n_out
        # Fresh nectar P ripens with first-order kinetics; ripe honey S cannot go below 0
        Pm, _ = lfilter([1], [1, -(1 - k_ripen)], intake, zi=[(1 - k_ripen) * P])
        ripe = k_ripen * Pm
        consumption = (0.05 / M) * (Nm / 1e4) + (0.04 / M) * (B / 1e4)  # kg/min
        cum = S + np.cumsum((1 - WATER_LOSS) * ripe - consumption + dS)
        Sm = cum - np.minimum(0, np.minimum.accumulate(np.minimum(cum, 0)))
        S, P = float(Sm[-1]), float(Pm[-1])
        # Management: supers, harvest, inspections (labeled; they disturb weight and temperature).
        # Never on a swarm/absconding day, so each labeled event keeps a clean signature.
        if any(ev["type"] in ("swarm", "absconding") and ev["start"].date() == idx[d * M].date() for ev in events[-2:]):
            todays = [x for x in todays if x != "inspection"]
            busy = True
        else:
            busy = False
        if cfg["events"]["supers"] and not busy and not dead and S > 0.7 * cap and bloom[d] > 0.5 and supers < 3:
            t0 = int(rng.uniform(9, 15) * 60)
            sw = rng.uniform(4, 5)
            supers, cap = supers + 1, cap + 15
            w_extra[t0:] += sw
            log("super_added", d * M + t0, d * M + t0 + 10, kg=round(sw, 2))
            todays = todays + ["inspection"]
        if cfg["events"]["harvest"] and not busy and supers and bloom[d] < 0.3 and d and bloom[d - 1] >= 0.3 and S > 12:
            t0 = int(rng.uniform(9, 14) * 60)
            kg = min(S - rng.uniform(8, 12), 15 * supers)
            if kg > 0:
                Sm[t0:] -= kg
                S -= kg
                log("harvest", d * M + t0, d * M + t0 + 30, kg=round(kg, 2))
                todays = todays + ["inspection"]
        if "inspection" in todays and not busy and not dead and S < cfg["events"]["feed_below_kg"]:
            t0, kg = int(rng.uniform(9, 15) * 60), rng.uniform(3, 5)  # sugar syrup, stored like nectar
            Sm[t0:] += kg
            S += kg
            log("feeding", d * M + t0, d * M + t0 + 10, kg=round(kg, 2))
        if "inspection" in todays and not dead:
            t0, dur = int(rng.uniform(8.5, 15) * 60), int(rng.uniform(10, 30))
            w = slice(t0, t0 + dur)
            w_extra[w] -= rng.uniform(1, 4) - rng.normal(0, 0.3, dur)  # frames out, hands on the box
            t_extra[w] -= rng.uniform(1, 4)
            log("inspection", d * M + t0, d * M + t0 + dur)
        brood_kg = np.linspace(B_prev, B, M) * 0.12e-3
        cols["weight"][sl] = (p["tare_kg"] + 4.5 * supers + Sm + Pm + M_BEE * (Nm - n_out) + brood_kg
                              + rainwater[sl] + w_extra)
        # Thermoregulation target; the probe follows it with a first-order lag (applied below)
        g_eff = min(1.0, p["gamma"] * np.sqrt(30000 / max(N, 1000)))
        heat = np.clip(T_out[sl] - 36, 0, 3) * 0.5
        solar = rad[sl] / 1000 * 1.5
        if dead:
            tt = T_out[sl] + solar
        elif B > 2000:
            tt = p["T_set"] + g_eff * (T_out[sl] - p["T_set"]) + heat + g_eff * solar
        else:
            ts_nb = p["T_set"] - 3
            tt = ts_nb + max(g_eff, 0.4) * (T_out[sl] - ts_nb) + solar * 0.5
        cols["T_target"][sl] = tt + t_extra
        rh_t = RH_out[sl] if dead else p["RH_set"] + p["a_rh"] * Pm / (Pm + 0.5) + p["b_rh"] * (RH_out[sl] - p["RH_set"])
        cols["RH_target"][sl] = rh_t + 0.8 * t_extra
        cols["traffic"][sl] = 2 * returns * (3 if rob_today else 1)
        cols["n_out"][sl] = n_out
        daily.append({"date": idx[d * M].date(), "hive_id": hive_id, "N": round(N), "B": round(B), "S_kg": S,
                      "P_kg": P, "supers": supers, "queen": "dead" if dead else queen, "bloom": bloom[d]})
    a = 1 / p["tau_T_min"]
    T_in = lfilter([a], [1, -(1 - a)], cols["T_target"], zi=[(1 - a) * cols["T_target"][0]])[0]
    a = 1 / p["tau_RH_min"]
    RH_in = lfilter([a], [1, -(1 - a)], cols["RH_target"], zi=[(1 - a) * cols["RH_target"][0]])[0]
    true = pd.DataFrame({"temp_in": T_in, "rh_in": np.clip(RH_in, 0, 100), "weight": cols["weight"],
                         "traffic": cols["traffic"], "temp_out": T_out, "rh_out": RH_out}, index=idx)
    params = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in p.items()}
    return true, pd.DataFrame(daily), events, params


def observe(cfg, true, hive_id, rng, events):
    """Sensor + node model: what the Prototype 1 node would actually report. docs/04-data/04-sensor-and-node-realism.md"""
    step = cfg["output_step_min"]
    t = true.iloc[::step]
    n = len(t)
    s, model = cfg["sensor"], SENSORS[cfg["sensor"]["model"]]
    out = pd.DataFrame(index=t.index)
    out["hive_id"] = hive_id
    q = np.full(n, "ok", dtype=object)
    for ch, key in (("temp_in", "t"), ("rh_in", "rh")):
        lo, hi, res, bias, sd = model[key]
        v = t[ch].values + rng.uniform(-bias, bias) + rng.normal(0, sd, n)
        if key == "rh":
            v += np.linspace(0, rng.uniform(0, 0.3) * n * step / (7 * M), n)  # slow fouling drift
        clipped = (v < lo) | (v > hi)
        v = np.round(np.clip(v, lo, hi) / res) * res
        out[ch + "_true"], out[ch] = t[ch].values, v
        out[ch + "_q"] = np.where(clipped, "clipped", "ok").astype(object)
    fail = rng.random(n) < s["read_fail_p"]  # one DHT11 read gives both values
    for ch in ("temp_in", "rh_in"):
        out.loc[fail, ch] = np.nan
        out.loc[fail, ch + "_q"] = "read_error"
    for _ in range(rng.poisson(s["stuck_per_year"] * n * step / (365 * M))):
        i0 = int(rng.integers(n))
        i1 = min(n, i0 + int(rng.lognormal(np.log(180 / step), 0.8)))
        for ch in ("temp_in", "rh_in"):
            out.iloc[i0:i1, out.columns.get_loc(ch)] = out[ch].iloc[i0]
            out.iloc[i0:i1, out.columns.get_loc(ch + "_q")] = "stuck"
        events.append({"hive_id": hive_id, "type": "sensor_stuck", "start": t.index[i0], "end": t.index[i1 - 1], "params": "{}"})
    hx = s["hx711"]
    gain, k_t = 1 + rng.uniform(-hx["gain_err"], hx["gain_err"]), u(rng, hx["temp_coeff_g_per_c"]) / 1000
    creep = np.linspace(0, u(rng, hx["creep_g_per_week"]) / 1000 * n * step / (7 * M), n)
    w = t["weight"].values * gain + k_t * (t["temp_out"].values - 25) + creep + rng.normal(0, hx["noise_g"] / 1000, n)
    spikes = rng.random(n) < hx["spike_per_day"] * step / M
    w[spikes] += rng.choice([-1, 1], spikes.sum()) * rng.uniform(0.2, 1.0, spikes.sum())
    out["weight_true"], out["weight"] = t["weight"].values, np.round(w / (hx["res_g"] / 1000)) * hx["res_g"] / 1000
    out["weight_q"] = "ok"
    # Node availability: dropouts (sensor), outages (power/network), clock after cold boot
    offline = np.zeros(n, bool)
    for _ in range(rng.poisson(s["dropout_per_week"] * n * step / (7 * M))):
        i0 = int(rng.integers(n))
        i1 = min(n, i0 + max(1, int(rng.lognormal(np.log(20 / step), 1.2))))
        for ch in ("temp_in", "rh_in"):
            out.iloc[i0:i1, out.columns.get_loc(ch)] = np.nan
            out.iloc[i0:i1, out.columns.get_loc(ch + "_q")] = "read_error"
        events.append({"hive_id": hive_id, "type": "sensor_dropout", "start": t.index[i0], "end": t.index[i1 - 1], "params": "{}"})
    nd = cfg["node"]
    if nd["power"] == "battery":
        e_wh = u(rng, nd["battery_wh"])
        hours = t.index.hour + t.index.minute / 60
        draw = np.where((hours > 6) & (hours < 18.5), nd["draw_w"]["day"], nd["draw_w"]["night"])
        left = e_wh
        for i in range(n):
            if hours[i] == nd["swap_hour"] and t.index[i].minute < step:
                left = e_wh  # someone swaps the battery
            left -= draw[i] * step / 60
            offline[i] = left <= 0
    else:
        for _ in range(rng.poisson(nd["outage_per_week"] * n * step / (7 * M))):
            i0 = int(rng.integers(n))
            offline[i0:i0 + max(1, int(rng.lognormal(np.log(nd["outage_median_h"] * 60 / step), 1.0)))] = True
    out["clock_offset_s"] = 0.0
    edges = np.flatnonzero(np.diff(np.r_[0, offline.astype(int), 0]))
    for i0, i1 in zip(edges[::2], edges[1::2]):
        events.append({"hive_id": hive_id, "type": "node_offline", "start": t.index[i0], "end": t.index[min(i1, n - 1)], "params": "{}"})
        # After boot the clock resumes from the time saved at shutdown until NTP syncs
        unsync = 1 if rng.random() > nd["ntp_slow_p"] else int(rng.uniform(5, 60) / step) + 1
        j1 = min(n, i1 + unsync)
        out.iloc[i1:j1, out.columns.get_loc("clock_offset_s")] = -(i1 - i0) * step * 60.0
        for ch in ("temp_in", "rh_in", "weight"):
            qcol = out.columns.get_loc(ch + "_q")
            ok = out.iloc[i1:j1, qcol] == "ok"
            out.iloc[np.arange(i1, j1)[ok.values], qcol] = "clock_unsynced"
    for ch in ("temp_in", "rh_in", "weight"):
        out.loc[offline, ch] = np.nan
        out.loc[offline, ch + "_q"] = "no_data"  # dataset-only flag: the real node sends nothing
    out["traffic_true"] = t["traffic"].values
    return out.reset_index(names="ts")


def run(cfg, seed, out_dir: Path):
    rng = np.random.default_rng(seed)
    days = cfg["period"]["days"]
    idx = pd.date_range(cfg["period"]["start"], periods=days * M, freq="min")
    wx = weather(cfg, idx, rng)
    bloom = bloom_curve(cfg, idx)
    tel, daily, events, params = [], [], [], {}
    for h in range(cfg["hives"]):
        hid = f"sim-{h:04d}"
        hr = np.random.default_rng([seed, h])
        true, dly, ev, prm = simulate_hive(cfg, hid, idx, wx, bloom, hr)
        tel.append(observe(cfg, true, hid, hr, ev))
        daily.append(dly)
        events += ev
        params[hid] = prm
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.concat(tel).to_parquet(out_dir / "telemetry.parquet", index=False)
    pd.DataFrame(events).sort_values(["hive_id", "start"]).to_parquet(out_dir / "events.parquet", index=False)
    pd.concat(daily).to_parquet(out_dir / "colony_daily.parquet", index=False)
    wx.iloc[::cfg["output_step_min"]].reset_index(names="ts").to_parquet(out_dir / "weather.parquet", index=False)
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    (out_dir / "manifest.json").write_text(json.dumps(
        {"generator": "simulation.telemetry.sim", "version": VERSION, "git": commit, "seed": seed,
         "tier": "S", "config": cfg, "hive_params": params}, indent=2, default=str))
    return out_dir


def load(path):
    return merge(DEFAULTS, yaml.safe_load(open(path)) if path else {})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", nargs="?")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    cfg = load(a.scenario)
    print(run(cfg, a.seed, a.out or Path("data/sim") / f"S-telemetry-{cfg['name']}-v{VERSION}-s{a.seed}"))
