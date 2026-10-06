# vision/

Training, evaluation, export and benchmarking of the pest detection models.

Status: Planned. Design is in [docs/03-vision/](../docs/03-vision/README.md).

Planned layout:

```text
vision/
├── configs/              Training configs per experiment (YAML)
├── train/                Stage 1 detector and stage 2 Varroa classifier
├── eval/                 Metrics per data tier (synthetic / public real / field)
├── export/               ONNX → NCNN conversion, INT8 calibration
├── bench/                Latency and memory benchmarks on the Pi 3B
└── notebooks/            Exploration only; nothing here is a source of truth
```

Synthetic training images are generated in [simulation/images](../simulation/README.md), not here.

Owner: Adrien Cubilla.
