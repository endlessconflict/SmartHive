"""Latency of our ncnn models, and an estimate for the Raspberry Pi 3B anchored to measured data.

We have no Pi in CI. ncnn publishes benchncnn timings for a Raspberry Pi 3 Model B+
(Cortex-A53, 1.4 GHz). We run the same reference graphs here with the same thread count,
take the median Pi/host ratio, apply it to our models and scale 1.4 -> 1.2 GHz for the 3B.
Replace with real numbers by running this script on the Pi (it prints measured times there).

    python -m vision.bench runs/stage1/<run>/weights/best_ncnn_model:320 runs/stage2/<run>/weights/best_ncnn_model:128
"""
import json
import platform
import statistics
import sys
import time
from pathlib import Path

import ncnn
import numpy as np

REF_DIR = Path("data/ncnn_ref")  # param files from github.com/Tencent/ncnn/tree/master/benchmark/models
# benchncnn, Raspberry Pi 3 Model B+, ms, avg (ncnn/benchmark/README.md)
PI3BP_MS = {4: {"squeezenet": 85.22, "mobilenet_v2": 111.68, "mobilenet_v3": 86.44, "shufflenet_v2": 47.19,
                "resnet18": 271.93, "mobilenet_ssd": 240.62, "yolov4-tiny": 417.17, "nanodet_m": 115.40, "yolo-fastestv2": 62.60},
            1: {"squeezenet": 125.58, "mobilenet_v2": 158.80, "mobilenet_v3": 127.23, "shufflenet_v2": 74.44,
                "resnet18": 379.57, "mobilenet_ssd": 425.93, "yolov4-tiny": 676.14, "nanodet_m": 178.64, "yolo-fastestv2": 79.84}}
PI3B_CLOCK_FACTOR = 1.4 / 1.2


def time_net(net, shape, input_name, outputs, loops=20):
    ex_in = np.random.default_rng(0).random(shape, dtype=np.float32)
    def once():
        ex = net.create_extractor()
        ex.input(input_name, ncnn.Mat(ex_in))
        for o in outputs:  # every head, or ncnn only computes the subgraph of one output
            ex.extract(o)
    for _ in range(3):
        once()
    ts = []
    for _ in range(loops):
        t = time.perf_counter()
        once()
        ts.append((time.perf_counter() - t) * 1e3)
    return statistics.median(ts)


def load(param, bin_=None, threads=4):
    net = ncnn.Net()
    net.opt.num_threads = threads
    net.opt.use_fp16_storage = True
    net.load_param(str(param))
    if bin_:
        net.load_model(str(bin_))
    else:
        net.load_model(ncnn.DataReaderFromEmpty())  # random-free zero weights: timing only
    return net


def ref_io(param):
    """ncnn param line: type name n_bottom n_top bottoms... tops... key=value..."""
    produced, consumed, inp, shape = [], set(), None, (3, 224, 224)
    for line in Path(param).read_text().splitlines()[2:]:
        t = line.split()
        if t[0] == "Noop":  # a marker layer some exports add after the real heads
            continue
        nb, nt = int(t[2]), int(t[3])
        consumed.update(t[4:4 + nb])
        produced += t[4 + nb:4 + nb + nt]
        if t[0] == "Input":
            kv = dict(x.split("=", 1) for x in t[4 + nb + nt:] if not x.startswith("-"))
            inp, shape = t[4 + nb], (int(kv.get("2", 3)), int(kv.get("1", 224)), int(kv.get("0", 224)))
    return inp, shape, [b for b in produced if b not in consumed]


def main(models):
    report = {"host": platform.processor() or platform.machine(), "pi": "Raspberry Pi 3 Model B (estimated)"}
    for threads in (4, 1):
        ratios = []
        for name, pi_ms in PI3BP_MS[threads].items():
            p = REF_DIR / f"{name}.param"
            inp, shape, outs = ref_io(p)
            host = time_net(load(p, threads=threads), shape, inp, outs)
            ratios.append(pi_ms / host)
        ratio = statistics.median(ratios)
        report[f"pi_over_host_t{threads}"] = {"median": round(ratio, 2), "min": round(min(ratios), 2), "max": round(max(ratios), 2)}
        for spec in models:
            folder, size = spec.rsplit(":", 1)
            net = load(Path(folder) / "model.ncnn.param", Path(folder) / "model.ncnn.bin", threads)
            host = time_net(net, (3, int(size), int(size)), "in0", ["out0"])
            key = f"{Path(folder).parent.parent.name}/{Path(folder).parent.parent.parent.name}"
            report.setdefault(key, {})[f"t{threads}"] = {
                "host_ms": round(host, 1),
                "pi3b_est_ms": round(host * ratio * PI3B_CLOCK_FACTOR, 0),
                "pi3b_est_range_ms": [round(host * min(ratios) * PI3B_CLOCK_FACTOR), round(host * max(ratios) * PI3B_CLOCK_FACTOR)]}
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main(sys.argv[1:])
