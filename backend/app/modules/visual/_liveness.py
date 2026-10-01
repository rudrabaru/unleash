"""
Visual Liveness: real EAR-based blink detection + landmark micro-movement +
face-tracking consistency. Replaces the standalone app's blendshape-based
blink signal per the Phase 2 decision (see implement-all-three-pillars plan).
"""
from typing import Any, Dict, List

import numpy as np

EAR_BLINK_THRESHOLD = 0.20
EAR_STD_THRESHOLD = 0.01


def _micro_movement(frames: List[Dict[str, Any]]) -> Dict[str, float]:
    movements = []
    previous = None

    for frame in frames:
        current = frame["landmarks"]
        if current is None:
            previous = None
            continue
        if previous is not None and previous.shape == current.shape:
            displacement = np.linalg.norm(current - previous, axis=1)
            movements.append(float(np.mean(displacement)))
        previous = current

    if not movements:
        return {"mean": 0.0, "std": 0.0, "samples": 0}

    values = np.asarray(movements, dtype=np.float32)
    return {"mean": float(np.mean(values)), "std": float(np.std(values)), "samples": len(values)}


<<<<<<< HEAD
def _ear_metrics(frames: List[Dict[str, Any]]) -> Dict[str, Any]:
    ear_values = [f["ear"] for f in frames if f.get("ear") is not None]
    if not ear_values:
        return {
            "detected": False,
            "min_ear": None,
            "mean": 0.0,
            "std": 0.0,
            "count": 0,
            "natural_movement_detected": False,
        }

    arr = np.asarray(ear_values, dtype=np.float32)
    ear_std = float(np.std(arr))
    ear_mean = float(np.mean(arr))
    blink_frames = [v for v in ear_values if v < EAR_BLINK_THRESHOLD]

    return {
        "detected": len(blink_frames) > 0,
        "min_ear": float(np.min(arr)),
        "mean": ear_mean,
        "std": ear_std,
        "count": len(blink_frames),
        "natural_movement_detected": bool(ear_std >= EAR_STD_THRESHOLD),
=======
def _blink_signal(frames: List[Dict[str, Any]]) -> Dict[str, Any]:
    ear_values = [f["ear"] for f in frames if f["ear"] is not None]
    if not ear_values:
        return {"detected": False, "min_ear": None, "count": 0}

    blink_frames = [v for v in ear_values if v < EAR_BLINK_THRESHOLD]
    return {
        "detected": len(blink_frames) > 0,
        "min_ear": min(ear_values),
        "count": len(blink_frames),
>>>>>>> origin/feature/deepfake-detection
    }


def _consistency(frames: List[Dict[str, Any]]) -> float:
    if not frames:
        return 0.0
    present = sum(1 for f in frames if f["face_present"])
    return present / len(frames)


def score_liveness(features: Dict[str, Any]) -> Dict[str, Any]:
    frames = features.get("frames", [])
    movement = _micro_movement(frames)
<<<<<<< HEAD
    ear = _ear_metrics(frames)
    consistency = _consistency(frames)

    blink_score = 1.0 if ear["detected"] else 0.0

    # Natural micro-movement:
    # 1. Landmark Euclidean displacement scaled linearly (mean ~0.001 - 0.005)
    movement_score = min(1.0, movement["mean"] * 200.0) if movement["samples"] else 0.0
    # 2. EAR variance sub-signal: EAR std >= EAR_STD_THRESHOLD indicates living, non-frozen eyes
    if ear["natural_movement_detected"]:
        movement_score = max(movement_score, 0.85)
=======
    blink = _blink_signal(frames)
    consistency = _consistency(frames)

    blink_score = 1.0 if blink["detected"] else 0.0
    # Natural micro-movement: EAR/landmark noise floor above EAR_STD_THRESHOLD
    # indicates a live, non-static face rather than a frozen photo/replay.
    movement_score = 1.0 if movement["std"] > EAR_STD_THRESHOLD or movement["mean"] > 0 else 0.0
    movement_score = min(1.0, movement["mean"] * 200.0) if movement["samples"] else 0.0
>>>>>>> origin/feature/deepfake-detection

    score = 0.4 * blink_score + 0.4 * movement_score + 0.2 * consistency
    score = max(0.0, min(1.0, score))

    return {
        "score": score,
        "passed": score >= 0.5,
<<<<<<< HEAD
        "blink_detected": ear["detected"],
        "natural_movement_detected": ear["natural_movement_detected"],
        "ear_std": ear["std"],
        "ear_mean": ear["mean"],
=======
        "blink_detected": blink["detected"],
>>>>>>> origin/feature/deepfake-detection
        "movement_mean": movement["mean"],
        "movement_std": movement["std"],
        "face_consistency_ratio": consistency,
        "frames_analyzed": len(frames),
    }
