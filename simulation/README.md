# simulation/

Synthetic data generators. There is no client data, so this folder produces all training data in the project, and (soon) the fake nodes used to develop the backend and dashboard.

| Part | Status | Entry point | Docs |
|---|---|---|---|
| `telemetry/` hive telemetry simulator | Implemented v1.0.0, 10 stylized-fact tests | `python -m simulation.telemetry.sim <scenario.yaml> --seed 42` | [04-data/02](../docs/04-data/02-hive-telemetry-simulator.md) |
| `images/render.py` procedural insect sprites | Implemented v0.1 | `python -m simulation.images.render` | [03-vision/03](../docs/03-vision/03-synthetic-image-pipeline.md) |
| `images/compose.py` entrance scenes + labels | Implemented v0.1 | `python -m simulation.images.compose --out data/sim/<name> --n 4000 --seed 1` | [03-vision/03](../docs/03-vision/03-synthetic-image-pipeline.md) |
| MQTT replay (fake nodes) | Planned (EN-02) | | [roadmap](../docs/roadmap.md) |

```text
simulation/
├── telemetry/
│   ├── sim.py            weather, colony, weight, temperature, humidity, events, sensor and node models
│   ├── scenarios/        baseline, swarm season, absconding/collapse, sensor faults, quiet hive, battery node
│   ├── figure.py         docs figure
│   └── test_sim.py       stylized facts
└── images/
    ├── render.py         procedural top-down insects (no photos, no license)
    ├── compose.py        boards, placement, occlusion-aware labels, camera model, stage 1/2 outputs
    └── test_images.py
```

Outputs go to `data/sim/` (git-ignored). Every generator takes a config and a seed, and the same pair always produces the same data.

```bash
pip install -r requirements.txt
python -m pytest simulation
```

Owners: Diego Alejandro Vasquez (telemetry), Adrien Cubilla (images), James Tack (replay).
