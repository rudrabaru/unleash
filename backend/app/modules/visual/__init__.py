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

from app.schemas.detector import DetectorResult
from app.schemas.session import VisualChallengeType
from app.modules.visual._landmarks import extract_landmark_features
from app.modules.visual._liveness import score_liveness
from app.modules.visual._pose import BLINK_TWICE_MIN_EVENTS, evaluate_challenge, YAW_THRESHOLD, PITCH_THRESHOLD


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


def verify_challenge_compliance(
    frames: List[Any],
    visual_challenge: str,
    features: Optional[Dict[str, Any]] = None,
) -> DetectorResult:
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

        result = evaluate_challenge(features, challenge)
        passed = bool(result["detected"])

        if "max_displacement" in result and "blink_events" not in result:
            denom = YAW_THRESHOLD if challenge in (VisualChallengeType.TURN_HEAD_LEFT, VisualChallengeType.TURN_HEAD_RIGHT) else PITCH_THRESHOLD
            score = max(0.0, min(1.0, result["max_displacement"] / denom))
        else:
            score = max(0.0, min(1.0, result.get("blink_events", 0) / BLINK_TWICE_MIN_EVENTS))

        reason = (
            f"Challenge {challenge.value} {'passed' if passed else 'failed'}: "
            f"required {result['threshold_desc']}."
        )

        return DetectorResult(
            score=round(score, 4),
            passed=passed,
            reason=reason,
            error=None,
            details={
                "visual_challenge": challenge.value,
                "complied": passed,
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

