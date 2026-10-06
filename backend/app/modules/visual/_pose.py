"""
Visual Challenge Compliance: yaw/pitch head-turn detection and blink-twice
detection, retargeted to the plan's thresholds (yaw +/-15, pitch +/-10)
instead of the standalone app's 20 degree/2-frame values.
"""
import statistics
from typing import Any, Dict, List

from app.modules.visual._landmarks import EAR_BLINK_THRESHOLD
from app.schemas.session import VisualChallengeType

YAW_THRESHOLD = 15.0
PITCH_THRESHOLD = 10.0
HOLD_FRAMES = 2
BASELINE_FRACTION = 0.2  # first ~20% of sampled frames act as the neutral baseline
BLINK_TWICE_MIN_EVENTS = 2
BLINK_LOOK_DOWN_DEG = 7.0  # pitch rise over baseline that invalidates a closed-eye stretch
BLINK_EXTREME_YAW_DEG = 25.0


def _baseline(frames: List[Dict[str, Any]], key: str) -> float | None:
    n = max(1, int(len(frames) * BASELINE_FRACTION))
    values = [f[key] for f in frames[:n] if f.get(key) is not None]
    if not values:
        values = [f[key] for f in frames if f.get(key) is not None]
    return statistics.median(values) if values else None


def _check_axis(frames, key, baseline, threshold, positive_qualifies) -> Dict[str, Any]:
    current_run = 0
    longest_run = 0
    max_displacement = 0.0
    valid_frames = 0

    for frame in frames:
        value = frame.get(key)
        if value is None:
            current_run = 0
            continue
        valid_frames += 1
        delta = value - baseline
        displacement = delta if positive_qualifies else -delta
        qualifies = displacement >= threshold
        max_displacement = max(max_displacement, max(0.0, displacement))
        if qualifies:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0

    return {
        "detected": longest_run >= HOLD_FRAMES,
        "max_displacement": max_displacement,
        "longest_run": longest_run,
        "valid_frames": valid_frames,
        "total_frames": len(frames),
    }


def _head_turn(frames, direction: str) -> Dict[str, Any]:
    baseline = _baseline(frames, "yaw")
    if baseline is None:
        return {"detected": False, "max_displacement": 0.0, "longest_run": 0, "valid_frames": 0, "total_frames": len(frames)}
    # Camera perspective: turning physical RIGHT -> positive yaw displacement, LEFT -> negative
    return _check_axis(frames, "yaw", baseline, YAW_THRESHOLD, positive_qualifies=(direction == "RIGHT"))


def _vertical_turn(frames, direction: str) -> Dict[str, Any]:
    baseline = _baseline(frames, "pitch")
    if baseline is None:
        return {"detected": False, "max_displacement": 0.0, "longest_run": 0, "valid_frames": 0, "total_frames": len(frames)}
    # looking DOWN -> positive pitch displacement, UP -> negative
    return _check_axis(frames, "pitch", baseline, PITCH_THRESHOLD, positive_qualifies=(direction == "DOWN"))


def _pose_corrupts_blink(frame, pitch_baseline, yaw_baseline) -> bool:
    """Looking down or turning far makes the eyelids read as closed without a blink."""
    pitch = frame.get("pitch")
    yaw = frame.get("yaw")
    looking_down = pitch is not None and pitch_baseline is not None and (pitch - pitch_baseline) >= BLINK_LOOK_DOWN_DEG
    extreme_yaw = yaw is not None and yaw_baseline is not None and abs(yaw - yaw_baseline) >= BLINK_EXTREME_YAW_DEG
    return looking_down or extreme_yaw


def _blink_twice(frames) -> Dict[str, Any]:
    """Count closed-eye stretches (EAR below threshold) as blinks.

    A stretch is judged as a whole: if the head is looking down or turned far at ANY frame of it,
    it is not a blink. Judging only the first frame let a downward glance count, because the eyes
    start to read as closed before the head has visibly moved.
    """
    events = 0
    in_dip = False
    dip_corrupted = False
    valid_frames = 0

    pitch_baseline = _baseline(frames, "pitch")
    yaw_baseline = _baseline(frames, "yaw")

    for frame in frames:
        value = frame.get("ear")
        if value is None:
            continue
        valid_frames += 1

        if value < EAR_BLINK_THRESHOLD:
            in_dip = True
            dip_corrupted = dip_corrupted or _pose_corrupts_blink(frame, pitch_baseline, yaw_baseline)
        elif in_dip:
            events += 0 if dip_corrupted else 1
            in_dip = False
            dip_corrupted = False

    if in_dip and not dip_corrupted:  # clip ended with the eyes still closed
        events += 1

    return {
        "detected": events >= BLINK_TWICE_MIN_EVENTS,
        "blink_events": events,
        "valid_frames": valid_frames,
        "total_frames": len(frames),
    }


def evaluate_challenge(features: Dict[str, Any], challenge: VisualChallengeType) -> Dict[str, Any]:
    frames = features.get("frames", [])

    if challenge == VisualChallengeType.TURN_HEAD_LEFT:
        result = _head_turn(frames, "LEFT")
        threshold_desc = f"yaw <= -{YAW_THRESHOLD} deg held {HOLD_FRAMES} frames"
    elif challenge == VisualChallengeType.TURN_HEAD_RIGHT:
        result = _head_turn(frames, "RIGHT")
        threshold_desc = f"yaw >= {YAW_THRESHOLD} deg held {HOLD_FRAMES} frames"
    elif challenge == VisualChallengeType.LOOK_UP:
        result = _vertical_turn(frames, "UP")
        threshold_desc = f"pitch <= -{PITCH_THRESHOLD} deg held {HOLD_FRAMES} frames"
    elif challenge == VisualChallengeType.LOOK_DOWN:
        result = _vertical_turn(frames, "DOWN")
        threshold_desc = f"pitch >= {PITCH_THRESHOLD} deg held {HOLD_FRAMES} frames"
    elif challenge == VisualChallengeType.BLINK_TWICE:
        result = _blink_twice(frames)
        threshold_desc = f">= {BLINK_TWICE_MIN_EVENTS} distinct blinks (EAR < {EAR_BLINK_THRESHOLD})"
    else:
        result = {"detected": False, "max_displacement": 0.0, "longest_run": 0, "valid_frames": 0, "total_frames": len(frames)}
        threshold_desc = "unknown challenge"

    result["threshold_desc"] = threshold_desc
    return result
