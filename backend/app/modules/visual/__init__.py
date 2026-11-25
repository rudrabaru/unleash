"""
Visual liveness and challenge verification
- Visual liveness detector (MediaPipe EAR + blink + micro-movement)
- Head pose and challenge compliance verifier (MediaPipe)

Both entrypoints accept an optional pre-computed `features` dict (from
`_landmarks.extract_landmark_features`) so a caller running MediaPipe once for several
consumers — the orchestrator runs it for liveness, challenge compliance, and the lip-sync
lip series, all over the same frame list — doesn't pay for three separate passes. Called
without it (e.g. tests exercising one function directly against raw frames), each function
still computes it itself; behavior and thresholds are unchanged either way.
"""
from typing import Any, Dict, List, Optional

from app.protocol import PhaseWindows
from app.schemas.detector import DetectorResult
from app.schemas.session import VisualChallengeType
from app.modules.visual._landmarks import extract_landmark_features
from app.modules.visual._liveness import score_liveness
from app.modules.visual._pose import BLINK_TWICE_MIN_EVENTS, evaluate_challenge, YAW_THRESHOLD, PITCH_THRESHOLD
from app.modules.visual._pose_phased import evaluate_challenge_phased, phased_reason


def detect_visual_liveness(
    frames: List[Any],
    features: Optional[Dict[str, Any]] = None,
) -> DetectorResult:
    if not frames:
        return DetectorResult(score=None, passed=False, reason="No video frames available.", error="empty frame list")

    try:
        if features is None:
            features = extract_landmark_features(frames)
        if features.get("error"):
            return DetectorResult(score=None, passed=False, reason="Face landmark extraction unavailable.", error=features["error"])

        result = score_liveness(features)
        reason = (
            f"Liveness score {result['score']:.2f}: blink={'yes' if result['blink_detected'] else 'no'}, "
            f"face tracked in {result['face_consistency_ratio']:.0%} of frames."
        )
        return DetectorResult(
            score=round(result["score"], 4),
            passed=result["passed"],
            reason=reason,
            error=None,
            details={
                "blink_detected": result["blink_detected"],
                "natural_movement_detected": result["natural_movement_detected"],
                "ear_std": round(result["ear_std"], 5),
                "ear_mean": round(result["ear_mean"], 4),
                "movement_mean": result["movement_mean"],
                "movement_std": result["movement_std"],
                "face_consistency_ratio": result["face_consistency_ratio"],
                "frames_analyzed": result["frames_analyzed"],
            },
        )
    except Exception as exc:  # noqa: BLE001 - a detector must never raise
        return DetectorResult(score=None, passed=False, reason="Visual liveness detection failed.", error=str(exc))


def _recording_start(features: Dict[str, Any], recording_start: Optional[float]) -> float:
    """Zero of the recording's clock: the one given, else the first timestamped frame, else 0."""
    if recording_start is not None:
        return recording_start
    times = [f["time_seconds"] for f in features.get("frames", []) if f.get("time_seconds") is not None]
    return min(times) if times else 0.0


def _challenge_score(challenge: VisualChallengeType, result: Dict[str, Any]) -> Optional[float]:
    """0-1 progress toward the asked action; None when the action could not be judged at all."""
    if "peak_displacement_deg" in result and "threshold_deg" in result:  # phase-aware head action
        return max(0.0, min(1.0, result["peak_displacement_deg"] / result["threshold_deg"]))
    if "max_displacement" in result and "blink_events" not in result:
        denom = YAW_THRESHOLD if challenge in (VisualChallengeType.TURN_HEAD_LEFT, VisualChallengeType.TURN_HEAD_RIGHT) else PITCH_THRESHOLD
        return max(0.0, min(1.0, result["max_displacement"] / denom))
    if "blink_events" in result:
        return max(0.0, min(1.0, result["blink_events"] / BLINK_TWICE_MIN_EVENTS))
    return None  # phase-aware check that could not judge (no face, bad baseline)


def verify_challenge_compliance(
    frames: List[Any],
    visual_challenge: str,
    features: Optional[Dict[str, Any]] = None,
    phases: Optional[PhaseWindows] = None,
    recording_start: Optional[float] = None,
) -> DetectorResult:
    """
    Check that the asked head action happened. With `phases` (the protocol windows) the action is
    judged inside the Act window as turn, hold and return, against a baseline taken in Read;
    without them the whole recording is judged as before. `recording_start` is the zero of the
    recording's clock (see app/media/probe.py).
    """
    if not frames:
        return DetectorResult(score=None, passed=False, reason="No video frames available.", error="empty frame list")

    try:
        challenge = VisualChallengeType(visual_challenge)
    except ValueError as exc:
        return DetectorResult(score=None, passed=False, reason=f"Unknown visual challenge '{visual_challenge}'.", error=str(exc))

    try:
        if features is None:
            features = extract_landmark_features(frames)
        if features.get("error"):
            return DetectorResult(score=None, passed=False, reason="Face landmark extraction unavailable.", error=features["error"])

        if phases is not None:
            result = evaluate_challenge_phased(features, challenge, phases, _recording_start(features, recording_start))
            reason = phased_reason(challenge, result)
        else:
            result = evaluate_challenge(features, challenge)
            reason = f"Challenge {challenge.value} {'passed' if result['detected'] else 'failed'}: required {result['threshold_desc']}."
        passed = bool(result["detected"])
        score = _challenge_score(challenge, result)

        return DetectorResult(
            score=None if score is None else round(score, 4),
            passed=passed,
            reason=reason,
            error=None,
            details={
                "visual_challenge": challenge.value,
                "complied": passed,
                "phase_aware": phases is not None,
                **{k: v for k, v in result.items() if k != "threshold_desc"},
            },
        )
    except Exception as exc:  # noqa: BLE001 - a detector must never raise
        return DetectorResult(score=None, passed=False, reason="Challenge compliance check failed.", error=str(exc))


__all__ = [
    "detect_visual_liveness",
    "verify_challenge_compliance",
    "extract_landmark_features",
]

