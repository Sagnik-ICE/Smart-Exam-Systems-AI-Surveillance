"""YOLO + MediaPipe FaceLandmarker eye tracking service.

Integrated from the user-provided monitoring model and adapted for API frame processing.
"""

from __future__ import annotations

import base64
import os
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from ultralytics import YOLO

# Landmark ids from user model.
LEFT_IRIS = [474, 475, 476, 477]
RIGHT_IRIS = [469, 470, 471, 472]

LEFT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
RIGHT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]

L_EYE_LEFT_CORNER = 362
L_EYE_RIGHT_CORNER = 263
R_EYE_LEFT_CORNER = 33
R_EYE_RIGHT_CORNER = 133
L_EYE_TOP = 386
L_EYE_BOTTOM = 374
R_EYE_TOP = 159
R_EYE_BOTTOM = 145

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)


@dataclass
class TrackerState:
    frame_count: int = 0
    alert_start: dict[str, float] = field(default_factory=dict)
    last_person_count: int = 0


class _ModelRuntime:
    def __init__(self):
        self._lock = threading.Lock()
        self._ready = False
        self.yolo: YOLO | None = None
        self.face_landmarker: Any = None

    def _ensure_model_file(self, model_path: str):
        if os.path.exists(model_path):
            return
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, model_path)

    def ensure_ready(self):
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return

            self.yolo = YOLO("yolov8n.pt")

            model_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "assets",
                "face_landmarker.task",
            )
            model_path = os.path.abspath(model_path)
            self._ensure_model_file(model_path)

            base_options = mp_python.BaseOptions(model_asset_path=model_path)
            face_options = mp_vision.FaceLandmarkerOptions(
                base_options=base_options,
                num_faces=1,
                min_face_detection_confidence=0.7,
                min_face_presence_confidence=0.7,
                min_tracking_confidence=0.7,
            )
            self.face_landmarker = mp_vision.FaceLandmarker.create_from_options(face_options)
            self._ready = True


_runtime = _ModelRuntime()
_trackers: dict[int, TrackerState] = {}
_trackers_lock = threading.Lock()
ALERT_DELAY_SECONDS = 0.35
YOLO_EVERY_N_FRAMES = 2


def _get_tracker(submission_id: int) -> TrackerState:
    with _trackers_lock:
        tracker = _trackers.get(submission_id)
        if tracker is None:
            tracker = TrackerState()
            _trackers[submission_id] = tracker
        return tracker


def _check_alert(tracker: TrackerState, key: str, condition: bool) -> bool:
    now = time.time()
    if condition:
        if key not in tracker.alert_start:
            tracker.alert_start[key] = now
            return False
        return now - tracker.alert_start[key] >= ALERT_DELAY_SECONDS
    tracker.alert_start.pop(key, None)
    return False


def _landmark_point(landmarks, idx: int, img_w: int, img_h: int) -> tuple[int, int]:
    lm = landmarks[idx]
    return int(lm.x * img_w), int(lm.y * img_h)


def _iris_center(landmarks, iris_ids: list[int], img_w: int, img_h: int) -> tuple[int, int]:
    pts = [_landmark_point(landmarks, idx, img_w, img_h) for idx in iris_ids]
    return int(np.mean([point[0] for point in pts])), int(np.mean([point[1] for point in pts]))


def _get_gaze_direction(landmarks, img_w: int, img_h: int) -> dict[str, Any]:
    left_iris_cx, left_iris_cy = _iris_center(landmarks, LEFT_IRIS, img_w, img_h)
    right_iris_cx, right_iris_cy = _iris_center(landmarks, RIGHT_IRIS, img_w, img_h)

    l_left = _landmark_point(landmarks, L_EYE_LEFT_CORNER, img_w, img_h)
    l_right = _landmark_point(landmarks, L_EYE_RIGHT_CORNER, img_w, img_h)
    r_left = _landmark_point(landmarks, R_EYE_LEFT_CORNER, img_w, img_h)
    r_right = _landmark_point(landmarks, R_EYE_RIGHT_CORNER, img_w, img_h)
    l_top = _landmark_point(landmarks, L_EYE_TOP, img_w, img_h)
    l_bottom = _landmark_point(landmarks, L_EYE_BOTTOM, img_w, img_h)
    r_top = _landmark_point(landmarks, R_EYE_TOP, img_w, img_h)
    r_bottom = _landmark_point(landmarks, R_EYE_BOTTOM, img_w, img_h)

    l_ratio = (left_iris_cx - l_left[0]) / (l_right[0] - l_left[0] + 1e-6)
    r_ratio = (right_iris_cx - r_left[0]) / (r_right[0] - r_left[0] + 1e-6)
    h_ratio = (l_ratio + r_ratio) / 2

    l_v_ratio = (left_iris_cy - l_top[1]) / (l_bottom[1] - l_top[1] + 1e-6)
    r_v_ratio = (right_iris_cy - r_top[1]) / (r_bottom[1] - r_top[1] + 1e-6)
    v_ratio = (l_v_ratio + r_v_ratio) / 2

    if h_ratio < 0.38:
        direction = "LOOKING LEFT"
    elif h_ratio > 0.62:
        direction = "LOOKING RIGHT"
    elif v_ratio < 0.35:
        direction = "LOOKING UP"
    elif v_ratio > 0.60:
        direction = "LOOKING DOWN"
    else:
        direction = "LOOKING CENTER"

    confidence = 0.95 if direction == "LOOKING CENTER" else 0.82
    return {
        "direction": direction,
        "h_ratio": float(h_ratio),
        "v_ratio": float(v_ratio),
        "left_iris": {"x": left_iris_cx, "y": left_iris_cy},
        "right_iris": {"x": right_iris_cx, "y": right_iris_cy},
        "confidence": confidence,
    }


def _alert_payload(alert_type: str, description: str, severity: str = "medium") -> dict[str, Any]:
    return {
        "type": alert_type,
        "severity": severity,
        "description": description,
    }


def process_student_frame(submission_id: int, frame_base64: str) -> dict[str, Any]:
    _runtime.ensure_ready()
    tracker = _get_tracker(submission_id)
    tracker.frame_count += 1

    timestamp_ms = int(datetime.now().timestamp() * 1000)

    try:
        frame_data = base64.b64decode(frame_base64)
        np_arr = np.frombuffer(frame_data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return {
                "status": "error",
                "error": "Failed to decode frame",
                "timestamp_ms": timestamp_ms,
                "frame_count": tracker.frame_count,
                "detections": {},
                "alerts": [],
                "metadata": {},
            }

        img_h, img_w = frame.shape[:2]

        if tracker.frame_count % YOLO_EVERY_N_FRAMES == 0:
            yolo_results = _runtime.yolo(frame, classes=[0], conf=0.45, verbose=False)
            tracker.last_person_count = sum(len(result.boxes) for result in yolo_results)
        person_count = tracker.last_person_count

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        face_results = _runtime.face_landmarker.detect(mp_image)

        gaze_direction = "NO FACE DETECTED"
        gaze_data: dict[str, Any] = {}
        alerts: list[dict[str, Any]] = []

        if face_results.face_landmarks:
            landmarks = face_results.face_landmarks[0]
            gaze_data = _get_gaze_direction(landmarks, img_w, img_h)
            gaze_direction = gaze_data["direction"]

            if _check_alert(tracker, "look_left", gaze_direction == "LOOKING LEFT"):
                alerts.append(_alert_payload("looking_left", "Student looking left", "medium"))
            if _check_alert(tracker, "look_right", gaze_direction == "LOOKING RIGHT"):
                alerts.append(_alert_payload("looking_right", "Student looking right", "medium"))
            if _check_alert(tracker, "look_up", gaze_direction == "LOOKING UP"):
                alerts.append(_alert_payload("looking_up", "Student looking up", "medium"))
            if _check_alert(tracker, "look_down", gaze_direction == "LOOKING DOWN"):
                alerts.append(_alert_payload("looking_down", "Student looking down", "medium"))
        else:
            if _check_alert(tracker, "no_face", True):
                alerts.append(_alert_payload("no_face_detected", "Face not visible", "high"))

        if _check_alert(tracker, "multi_person", person_count > 1):
            alerts.append(_alert_payload("multiple_people", "Multiple people detected", "high"))
        if _check_alert(tracker, "no_person", person_count == 0):
            alerts.append(_alert_payload("no_person", "No person detected in frame", "high"))

        return {
            "status": "success",
            "timestamp_ms": timestamp_ms,
            "frame_count": tracker.frame_count,
            "detections": {
                "person_count": person_count,
                "gaze_direction": gaze_direction,
                "gaze_data": gaze_data,
                "face_detected": bool(face_results.face_landmarks),
            },
            "alerts": alerts,
            "metadata": {
                "frame_width": img_w,
                "frame_height": img_h,
            },
        }
    except Exception as error:
        return {
            "status": "error",
            "error": f"Frame processing error: {str(error)}",
            "timestamp_ms": timestamp_ms,
            "frame_count": tracker.frame_count,
            "detections": {},
            "alerts": [],
            "metadata": {},
        }


def reset_tracker(submission_id: int | None = None):
    with _trackers_lock:
        if submission_id is None:
            _trackers.clear()
            return
        _trackers.pop(submission_id, None)
