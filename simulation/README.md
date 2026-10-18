# simulation/

Synthetic hive telemetry. There is no client data, so this folder produces the fake hives used to develop the backend, the dashboard and the time-series models. The synthetic *image* generator moved to [SmartHive-Vision](https://github.com/endlessconflict/SmartHive-Vision) together with the detector it trains.

| Part | Status | Entry point | Docs |
|---|---|---|---|
| `telemetry/` hive telemetry simulator | Implemented v1.0.0, 10 stylized-fact tests | `python -m simulation.telemetry.sim <scenario.yaml> --seed 42` | [04-data/02](../docs/04-data/02-hive-telemetry-simulator.md) |
| MQTT replay (fake nodes) | Planned (EN-02) | | [roadmap](../docs/roadmap.md) |

```text
simulation/
└── telemetry/
    ├── sim.py            weather, colony, weight, temperature, humidity, events, sensor and node models
    ├── scenarios/        baseline, swarm season, absconding/collapse, sensor faults, quiet hive, battery node
    ├── figure.py         docs figure
    └── test_sim.py       stylized facts
```

Outputs go to `data/sim/` (git-ignored). Every generator takes a config and a seed, and the same pair always produces the same data.

```bash
pip install -r simulation/requirements.txt
python -m pytest simulation
```

Owners: Diego Alejandro Vasquez (signal models), James Tack (replay).
