"""
Shared MediaPipe FaceLandmarker wrapper for the visual module.

Ported from `Liveliness + challenge/video_process.py` (Dev 2's standalone app),
adapted to run on a pre-sampled RGB frame list (from the shared frame loader)
instead of decoding the video itself, and switched to IMAGE running mode since
sampled frames are not temporally contiguous.
"""
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    MEDIAPIPE_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only if mediapipe isn't installed
    MEDIAPIPE_AVAILABLE = False

MODEL_PATH = Path(__file__).parent / "face_landmarker.task"

# Standard MediaPipe FaceMesh 6-point eye contours for EAR.
LEFT_EYE = (33, 160, 158, 133, 153, 144)
RIGHT_EYE = (362, 385, 387, 263, 373, 380)

# Mouth vertical/horizontal points (used by _lip_series and challenge compliance).
MOUTH_TOP, MOUTH_BOTTOM = 13, 14
MOUTH_LEFT, MOUTH_RIGHT = 61, 291
FACE_TOP, FACE_CHIN = 10, 152

_landmarker_singleton = None


def _get_landmarker():
    global _landmarker_singleton
    if _landmarker_singleton is None:
        options = mp_vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(MODEL_PATH)),
            running_mode=mp_vision.RunningMode.IMAGE,
            num_faces=1,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=True,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        _landmarker_singleton = mp_vision.FaceLandmarker.create_from_options(options)
    return _landmarker_singleton


def _rotation_matrix_to_euler(matrix) -> tuple:
    r00, r02 = matrix[0][0], matrix[0][2]
    r10, r11, r12 = matrix[1][0], matrix[1][1], matrix[1][2]

    yaw = math.atan2(r02, r00)
    pitch = math.atan2(-r12, r11)
    roll = math.atan2(r10, math.sqrt(r00 * r00 + r02 * r02))

    return math.degrees(yaw), math.degrees(pitch), math.degrees(roll)


def _ear(landmarks: np.ndarray, points: tuple) -> Optional[float]:
    p1, p2, p3, p4, p5, p6 = (landmarks[i] for i in points)
    vertical = np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)
    horizontal = np.linalg.norm(p1 - p4)
    if horizontal < 1e-6:
        return None
    return float(vertical / (2.0 * horizontal))


def extract_landmark_features(
    frames: List[np.ndarray],
    timestamps: Optional[List[float]] = None,
    original_indices: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Run the FaceLandmarker over each already-sampled RGB frame independently
    (IMAGE mode) and return per-frame pose/EAR/mouth metrics.

    Never raises: a frame that fails to process yields a "no face" entry.
    """
    if not MEDIAPIPE_AVAILABLE:
        return {"frames": [], "error": "mediapipe is not installed"}

    landmarker = _get_landmarker()
    frame_data = []

    for i, frame_rgb in enumerate(frames):
        time_sec = timestamps[i] if timestamps and i < len(timestamps) else None
        orig_idx = original_indices[i] if original_indices and i < len(original_indices) else i

        entry: Dict[str, Any] = {
            "landmarks": None,
            "face_present": False,
            "yaw": None,
            "pitch": None,
            "roll": None,
            "ear_left": None,
            "ear_right": None,
            "ear": None,
            "mouth_open": None,
            "time_seconds": time_sec,
            "original_index": orig_idx,
        }

        try:
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            result = landmarker.detect(mp_image)
        except Exception:
            frame_data.append(entry)
            continue

        if result.face_landmarks:
            landmarks = np.array(
                [[lm.x, lm.y] for lm in result.face_landmarks[0]], dtype=np.float32
            )
            entry["landmarks"] = landmarks
            entry["face_present"] = True

            # Convert to pixel coordinates for aspect-ratio invariant geometry (EAR & mouth)
            h, w = frame_rgb.shape[:2]
            px_landmarks = landmarks * np.array([w, h], dtype=np.float32)

            ear_left = _ear(px_landmarks, LEFT_EYE)
            ear_right = _ear(px_landmarks, RIGHT_EYE)
            entry["ear_left"] = ear_left
            entry["ear_right"] = ear_right
            if ear_left is not None and ear_right is not None:
                entry["ear"] = (ear_left + ear_right) / 2.0

            face_height = np.linalg.norm(px_landmarks[FACE_TOP] - px_landmarks[FACE_CHIN])
            mouth_gap = np.linalg.norm(px_landmarks[MOUTH_TOP] - px_landmarks[MOUTH_BOTTOM])
            if face_height > 1e-6:
                entry["mouth_open"] = float(mouth_gap / face_height)

        if result.facial_transformation_matrixes:
            yaw, pitch, roll = _rotation_matrix_to_euler(result.facial_transformation_matrixes[0])
            entry["yaw"], entry["pitch"], entry["roll"] = yaw, pitch, roll

        frame_data.append(entry)

    return {"frames": frame_data, "error": None}
