# ============================================================
# vision/vision.py — YOLOv8n ONNX inference engine
# ============================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import cv2
import numpy as np

from utils.logger import setup_logger

log = setup_logger(__name__)


@dataclass
class Detection:
    label:      str
    confidence: float
    bbox:       Tuple[int, int, int, int]   # x1, y1, x2, y2

    @property
    def center(self) -> Tuple[int, int]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    def to_dict(self) -> dict:
        return {
            "label":      self.label,
            "confidence": round(self.confidence, 3),
            "bbox":       list(self.bbox),
            "center":     list(self.center),
        }


class VisionEngine:
    def __init__(
        self,
        model_path:  str,
        class_map:   Dict[int, str],
        conf_thresh: float = 0.40,
        iou_thresh:  float = 0.45,
        input_size:  int   = 640,
    ):
        self.class_map   = class_map
        self.conf_thresh = conf_thresh
        self.iou_thresh  = iou_thresh
        self.input_size  = input_size
        self._session    = None

        try:
            import onnxruntime as ort
            self._session = ort.InferenceSession(
                model_path,
                providers=["CPUExecutionProvider"]
            )
            self._input_name = self._session.get_inputs()[0].name
            log.info(f"VisionEngine loaded: {model_path}")
        except Exception as e:
            log.warning(f"ONNX model not loaded ({e}). Running in stub mode — empty detections.")

    def _preprocess(self, frame: np.ndarray) -> np.ndarray:
        img   = cv2.resize(frame, (self.input_size, self.input_size))
        img   = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img   = img.astype(np.float32) / 255.0
        return np.expand_dims(img.transpose(2, 0, 1), axis=0)

    def _postprocess(
        self,
        outputs:      np.ndarray,
        orig_w:       int,
        orig_h:       int,
    ) -> List[Detection]:
        """
        YOLOv8 output shape: [1, num_classes+4, num_anchors]
        Each column: [cx, cy, w, h, cls0_score, cls1_score, ...]
        """
        preds = outputs[0][0].T          # [num_anchors, 4+num_classes]
        results: List[Detection] = []

        sx = orig_w / self.input_size
        sy = orig_h / self.input_size

        for row in preds:
            scores    = row[4:]
            cls_id    = int(np.argmax(scores))
            conf      = float(scores[cls_id])
            if conf < self.conf_thresh:
                continue

            cx, cy, w, h = row[:4]
            x1 = int((cx - w / 2) * sx)
            y1 = int((cy - h / 2) * sy)
            x2 = int((cx + w / 2) * sx)
            y2 = int((cy + h / 2) * sy)

            label = self.class_map.get(cls_id, str(cls_id))
            results.append(Detection(label=label, confidence=conf, bbox=(x1, y1, x2, y2)))

        return self._nms(results)

    def _nms(self, detections: List[Detection]) -> List[Detection]:
        if not detections:
            return []
        boxes  = np.array([d.bbox for d in detections], dtype=np.float32)
        scores = np.array([d.confidence for d in detections], dtype=np.float32)
        idxs   = cv2.dnn.NMSBoxes(
            boxes.tolist(), scores.tolist(),
            self.conf_thresh, self.iou_thresh
        )
        return [detections[i] for i in (idxs.flatten() if len(idxs) else [])]

    def analyze(self, frame: np.ndarray) -> List[Detection]:
        if self._session is None:
            return []
        try:
            blob    = self._preprocess(frame)
            outputs = self._session.run(None, {self._input_name: blob})
            h, w    = frame.shape[:2]
            return self._postprocess(outputs, w, h)
        except Exception as e:
            log.error(f"VisionEngine.analyze error: {e}")
            return []

    def annotate(self, frame: np.ndarray, detections: List[Detection]) -> np.ndarray:
        out = frame.copy()
        for d in detections:
            x1, y1, x2, y2 = d.bbox
            cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(out, f"{d.label} {d.confidence:.2f}",
                        (x1, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
        return out
