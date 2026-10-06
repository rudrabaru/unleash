"""
Face crops for the deepfake classifier, taken from the landmarks the visual detectors already
computed (landmark coordinates are normalised, so they apply to a frame of any resolution and no
second MediaPipe run is needed).

A frame whose landmarks are missing is skipped: it is never replaced by the whole frame.
"""
from typing import Any, Dict, List, Optional

import numpy as np

# Side of the crop relative to the larger side of the landmark bounding box. 1.3 is the usual
# face-forensics crop scale: the whole face plus a little context at the hairline and jaw.
CROP_SCALE = 1.3
# Crops smaller than this (in pixels, native frame) carry too little detail to classify.
MIN_CROP_PIXELS = 64


def face_box(landmarks: np.ndarray, width: int, height: int, scale: float = CROP_SCALE) -> Optional[tuple]:
    """Square (x0, y0, x1, y1) pixel box around normalised landmarks, clamped to the frame."""
    if landmarks is None or len(landmarks) == 0:
        return None
    mins, maxs = landmarks.min(axis=0), landmarks.max(axis=0)
    center_x, center_y = (mins + maxs) / 2.0 * np.array([width, height])
    side = max((maxs[0] - mins[0]) * width, (maxs[1] - mins[1]) * height) * scale
    half = side / 2.0
    x0, x1 = int(round(max(0.0, center_x - half))), int(round(min(float(width), center_x + half)))
    y0, y1 = int(round(max(0.0, center_y - half))), int(round(min(float(height), center_y + half)))
    if x1 - x0 < MIN_CROP_PIXELS or y1 - y0 < MIN_CROP_PIXELS:
        return None
    return x0, y0, x1, y1


def crop_faces(
    frames: List[np.ndarray],
    frame_indices: List[int],
    landmark_features: Optional[Dict[str, Any]],
) -> List[np.ndarray]:
    """
    Crop the face out of each frame. `frame_indices[i]` is the stream position of `frames[i]`;
    it is matched to the landmark entry with the same `original_index`. Frames without a
    usable face are left out, so the result can be shorter than `frames` (or empty).
    """
    if not landmark_features or landmark_features.get("error"):
        return []
    by_index = {entry["original_index"]: entry for entry in landmark_features["frames"] if entry["face_present"]}

    crops = []
    for frame, index in zip(frames, frame_indices):
        entry = by_index.get(index)
        if entry is None:
            continue
        height, width = frame.shape[:2]
        box = face_box(entry["landmarks"], width, height)
        if box is not None:
            x0, y0, x1, y1 = box
            crops.append(frame[y0:y1, x0:x1])
    return crops
