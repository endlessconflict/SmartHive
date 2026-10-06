"""Train the two stages with the project defaults. Design: docs/03-vision/04-model-architecture.md

    python -m vision.train stage1 data/sim/S-images-entrance-v0.1-s1 --epochs 40
    python -m vision.train stage2 data/sim/S-images-entrance-v0.1-s1 --epochs 20

Runs land in runs/<stage>/<name>; weights/best.pt is what export.py converts for the Pi.
"""
import argparse
import json
from pathlib import Path

import yaml
from ultralytics import YOLO

WEIGHTS = Path("data/weights")  # COCO / ImageNet pretrained checkpoints (transfer learning)
DEFAULTS = {
    # 320 px input: a bee is ~20 px, enough for stage 1; Varroa is left to stage 2 on full-res crops
    "stage1": dict(model="yolo11n.pt", imgsz=320, batch=32, mosaic=1.0, close_mosaic=5, degrees=180, flipud=0.5,
                   fliplr=0.5, hsv_h=0.02, hsv_s=0.5, hsv_v=0.4, scale=0.3, translate=0.1),
    "stage2": dict(model="yolo11n-cls.pt", imgsz=128, batch=128, degrees=180, flipud=0.5, fliplr=0.5,
                   hsv_h=0.02, hsv_s=0.4, hsv_v=0.4, erasing=0.0),  # erasing could delete the only mite
}


def main(stage, dataset: Path, epochs, name, extra):
    cfg = dict(DEFAULTS[stage], **extra)
    model = YOLO(str(WEIGHTS / cfg.pop("model")))
    data = dataset / "stage1/data.yaml" if stage == "stage1" else dataset / "stage2"
    res = model.train(data=str(data), epochs=epochs, project=str(Path("runs") / stage), name=name, exist_ok=True,
                      device="cpu", workers=4, seed=0, deterministic=True, plots=True, **cfg)
    run = Path(res.save_dir)
    (run / "smarthive.json").write_text(json.dumps({"stage": stage, "dataset": dataset.name, "epochs": epochs,
                                                    "config": cfg, "metrics": res.results_dict}, indent=2, default=str))
    print(run)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["stage1", "stage2"])
    ap.add_argument("dataset", type=Path)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--name")
    ap.add_argument("--set", nargs="*", default=[], help="extra ultralytics args, key=value")
    a = ap.parse_args()
    extra = {k: yaml.safe_load(v) for k, v in (s.split("=", 1) for s in a.set)}
    main(a.stage, a.dataset, a.epochs, a.name or a.dataset.name, extra)
