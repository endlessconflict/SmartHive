"""Export trained weights to ncnn for the node (PyTorch -> TorchScript -> pnnx -> ncnn).

    python -m vision.export runs/stage1/<run>/weights/best.pt --imgsz 320
    python -m vision.export runs/stage2/<run>/weights/best.pt --imgsz 128

Writes <run>/weights/best_ncnn_model/{model.ncnn.param, model.ncnn.bin, metadata.yaml}.
"""
import argparse
from pathlib import Path

from ultralytics import YOLO

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("weights", type=Path)
    ap.add_argument("--imgsz", type=int, required=True)
    a = ap.parse_args()
    # ponytail: fp32 weights + fp16 storage at runtime; ncnn int8 needs the C++ ncnn2int8 tools, add if latency demands it
    print(YOLO(str(a.weights)).export(format="ncnn", imgsz=a.imgsz, half=False, device="cpu"))
