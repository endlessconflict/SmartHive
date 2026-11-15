"""The pest and threat detector of the project: YOLO11n v2 from Smart-Hive-DSD-20262/Pest_Threats_Detection.

Three classes, `bee`, `varroa` and `wasp` (wasps and hornets are one class there). The checkpoint
`models/runs/yolo11n_v2/weights/best.pt` of that repository was exported to ONNX once (see model/README.md);
this module runs the ONNX file with onnxruntime, so the node image needs no PyTorch.

Pre- and post-processing follow the repository's inference notebook: 640 x 640 letterbox, confidence 0.25,
IoU 0.45 for the non-maximum suppression.
"""

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

CLASSES = ("bee", "varroa", "wasp")
IMGSZ = 640


class PestDetector:
    def __init__(self, model: Path, conf: float = 0.25, iou: float = 0.45, threads: int = 2) -> None:
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        self.session = ort.InferenceSession(str(model), opts, providers=["CPUExecutionProvider"])
        self.input = self.session.get_inputs()[0].name
        self.conf, self.iou = conf, iou

    def __call__(self, bgr: np.ndarray) -> list[dict]:
        """Detections of one frame (OpenCV BGR): [{"cls", "conf", "box": [x1, y1, x2, y2]}] in frame pixels."""
        h, w = bgr.shape[:2]
        k = IMGSZ / max(h, w)
        nw, nh = round(w * k), round(h * k)
        canvas = np.full((IMGSZ, IMGSZ, 3), 114, np.uint8)
        top, left = (IMGSZ - nh) // 2, (IMGSZ - nw) // 2
        canvas[top : top + nh, left : left + nw] = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
        x = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).transpose(2, 0, 1)[None].astype(np.float32) / 255
        out = self.session.run(None, {self.input: x})[0][0].T  # 8400 rows: cx, cy, w, h, then a score per class
        scores = out[:, 4:]
        cls = scores.argmax(1)
        conf = scores.max(1)
        keep = conf >= self.conf
        out, cls, conf = out[keep], cls[keep], conf[keep]
        if not len(out):
            return []
        boxes = np.stack([out[:, 0] - out[:, 2] / 2, out[:, 1] - out[:, 3] / 2, out[:, 2], out[:, 3]], 1)
        picked = cv2.dnn.NMSBoxesBatched(boxes.tolist(), conf.tolist(), cls.tolist(), self.conf, self.iou)
        result = []
        for i in np.array(picked).reshape(-1):
            x0, y0, bw, bh = boxes[i]
            box = [(x0 - left) / k, (y0 - top) / k, (x0 + bw - left) / k, (y0 + bh - top) / k]
            box = [round(float(np.clip(v, 0, m))) for v, m in zip(box, (w, h, w, h))]
            result.append({"cls": CLASSES[int(cls[i])], "conf": round(float(conf[i]), 3), "box": box})
        return sorted(result, key=lambda o: -o["conf"])
