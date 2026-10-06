# simulation/

Synthetic data generators. Because there is no client data, this folder produces all training data in the project, and the fake nodes used to develop the backend and dashboard.

Status: Planned. Design is in [docs/04-data/](../docs/04-data/README.md) and [docs/03-vision/03-synthetic-image-pipeline.md](../docs/03-vision/03-synthetic-image-pipeline.md).

```text
simulation/
├── images/               Synthetic entrance images with labels
│   ├── assets/           Asset manifest (sources and licenses); files tracked by DVC
│   ├── compositor/       2D cut-and-paste generator (main path)
│   ├── render/           Blender/BlenderProc scenes (optional path)
│   └── configs/
├── telemetry/            Hive telemetry simulator
│   ├── models/           Weather, colony, thermal, humidity, weight
│   ├── events/           Swarming, absconding, harvest, sensor faults...
│   ├── sensors/          DHT11, HX711 and node behavior models
│   └── scenarios/        YAML scenario files
└── replay/               Publishes simulated hives over MQTT as fake nodes
```

Owners: Adrien Cubilla (images), Diego Alejandro Vasquez (telemetry), James Tack (replay).

Rule: every generator takes a config file and a seed, and the same pair always produces the same data.
