# Detector model

`yolo11n_v2.onnx` is the YOLO11n v2 pest and threat detector of the project, trained by Diego Alejandro
Vásquez and published in [Smart-Hive-DSD-20262/Pest_Threats_Detection](https://github.com/Smart-Hive-DSD-20262/Pest_Threats_Detection).

| | |
|---|---|
| Source checkpoint | `models/runs/yolo11n_v2/weights/best.pt`, commit `bdef3c2e11a3c5d24548890930fa1df8d708fb1b` |
| SHA-256 of `best.pt` | `d590766ccc40858cdaefb122f2cb819b0c527ea44a5ee30862a486c0f3b269b5` |
| Classes | `0 bee`, `1 varroa`, `2 wasp` (wasps and hornets are one class) |
| Input / output | `images` 1x3x640x640 RGB 0..1 / `output0` 1x7x8400 (cx, cy, w, h, three class scores) |
| Reported validation | 143 images, 183 instances: P 0.984, R 0.988, mAP@50 0.985, mAP@50-95 0.752 (varroa mAP@50-95 0.636) |

## How the ONNX file was made

```bash
pip install ultralytics==8.3.0 onnx onnxslim onnxruntime onnxscript
python -c "from ultralytics import YOLO; YOLO('best.pt').export(format='onnx', imgsz=640, simplify=True, opset=18)"
# the exporter writes the weights beside the graph; fold them into one file
# and lower the IR version to 10, which onnxruntime 1.20 reads (opset 18 is unchanged)
python -c "import onnx; m = onnx.load('best.onnx'); m.ir_version = 10; onnx.save_model(m, 'yolo11n_v2.onnx', save_as_external_data=False)"
```

To use a newer checkpoint, repeat this with the new `best.pt`, replace the file, update the table above and run
`demo/verify`. The node image runs it with onnxruntime (`../detector.py`); on the Raspberry Pi the same
checkpoint can be exported to ncnn with `format='ncnn'`.

## What the demo claims, and what it does not

The model was trained on BeeAlarmed BeeDataset photographs and the demo frames (`../corpus`) are other photographs
of the same dataset, so the demo shows that the *pipeline* works with the project's model, not how accurate the
model is in a real hive. The validation set is small and the author lists a possible train/validation leakage
among its limitations; see the repository's `docs/03_TRAINING_RESULTS.md`.
