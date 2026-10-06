"""Docs figure: a few days of one simulated hive, true vs observed, with labeled events.

    python -m simulation.telemetry.figure data/sim/S-telemetry-swarm_season-v1.0.0-s42 docs/assets/data/telemetry-swarm-week.png
"""
import json
import sys
from pathlib import Path

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e0"
TRUE, OBS = "#2a78d6", "#eb6834"  # categorical slots 1 and 2 (dataviz reference palette)


def main(ds: Path, out: Path, days: int = 4):
    t = pd.read_parquet(ds / "telemetry.parquet")
    e = pd.read_parquet(ds / "events.parquet")
    params = json.loads((ds / "manifest.json").read_text())["hive_params"]
    sw = e[(e.type == "swarm") & e.hive_id.map(lambda h: params[h]["position"] == "brood_center")].iloc[0]
    start = sw.start.normalize() - pd.Timedelta(days=1)
    end = start + pd.Timedelta(days=days)
    x = t[(t.hive_id == sw.hive_id) & t.ts.between(start, end)]
    ev = e[(e.hive_id == sw.hive_id) & (e.start < end) & (e.end > start) & ~e.type.str.startswith("sensor")]
    panels = [("temp_in", "Brood temperature (°C)"), ("rh_in", "Brood humidity (% RH)"), ("weight", "Hive weight (kg)")]
    fig, axes = plt.subplots(3, 1, figsize=(10, 7.5), sharex=True, facecolor=SURFACE)
    for ax, (ch, label) in zip(axes, panels):
        ax.set_facecolor(SURFACE)
        for r in ev.itertuples():
            ax.axvspan(r.start, max(r.end, r.start + pd.Timedelta(minutes=20)), color=GRID, lw=0)
        ax.plot(x.ts, x[ch + "_true"], color=TRUE, lw=2, label="true value (simulator)")
        ax.plot(x.ts, x[ch], ".", color=OBS, ms=3, label="what the node reports (DHT11 / HX711)")
        ax.set_ylabel(label, color=MUTED)
        ax.tick_params(colors=MUTED)
        ax.grid(axis="y", color=GRID, lw=0.8)
        for s in ax.spines.values():
            s.set_visible(False)
    for r in ev.itertuples():
        axes[0].annotate(r.type.replace("_", " "), (r.start, 1.02), xycoords=("data", "axes fraction"),
                         color=INK, fontsize=9, ha="left", va="bottom")
    axes[0].legend(loc="lower left", frameon=False, fontsize=9, labelcolor=INK, ncol=2)
    fig.suptitle(f"Simulated hive {sw.hive_id}, probe at brood center: swarm on {sw.start:%Y-%m-%d %H:%M} (tier S, synthetic)",
                 color=INK, x=0.01, ha="left")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130, facecolor=SURFACE)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
