"""
Evidence Fusion + Decision Engine.

Combines the five detector signals (visual liveness, visual challenge compliance,
deepfake, replay, audio) into a final verdict, per docs/unleash_project_plan.md
Section 6 and docs/unleash_team_companion_guide.md Section 2.5.
"""
from dataclasses import dataclass
from typing import Dict, Optional

from app.schemas.detector import DetectorResult
from app.schemas.session import VerificationStatus

# Weighted-scoring portion. Challenge compliance's must-pass check is separate from its
# score weight; the audio speech and phrase checks are pure must-pass checks with no
# weight of their own (they decide audio_pipeline.passed instead).
SIGNAL_WEIGHTS: Dict[str, float] = {
    "visual_liveness": 0.20,
    "visual_challenge": 0.25,
    "deepfake": 0.20,
    "replay": 0.15,
    "voice_authenticity": 0.10,
    "av_alignment": 0.10,
}

VERIFIED_THRESHOLD = 0.80
SUSPICIOUS_THRESHOLD = 0.55

JOINT_VETO_DEEPFAKE_THRESHOLD = 0.3
JOINT_VETO_REPLAY_THRESHOLD = 0.4


@dataclass
class FusionResult:
    status: VerificationStatus
    confidence: Optional[float]
    reason: str


def _must_pass_failed(signals: Dict[str, DetectorResult]) -> Optional[str]:
    """Return a human-readable reason if any must-pass check failed, else None."""
    visual_challenge = signals.get("visual_challenge")
    if visual_challenge is not None and not visual_challenge.passed:
        return f"Visual challenge compliance failed: {visual_challenge.reason}"

    audio = signals.get("audio_pipeline")
    if audio is not None and not audio.passed:
        return f"Audio must-pass check failed: {audio.reason}"

    deepfake = signals.get("deepfake")
    replay = signals.get("replay")
    if (
        deepfake is not None and deepfake.score is not None
        and replay is not None and replay.score is not None
        and deepfake.score < JOINT_VETO_DEEPFAKE_THRESHOLD
        and replay.score < JOINT_VETO_REPLAY_THRESHOLD
    ):
        return (
            f"Joint veto: deepfake score {deepfake.score:.2f} < "
            f"{JOINT_VETO_DEEPFAKE_THRESHOLD} and replay score {replay.score:.2f} < "
            f"{JOINT_VETO_REPLAY_THRESHOLD}"
        )

    return None


def _weighted_score(signals: Dict[str, DetectorResult]) -> Optional[float]:
    """
    Weighted average of the six soft/advisory signals. Null scores are excluded
    and their weight redistributed proportionally across the remaining signals
    (never treated as 0), per plan Section 6.

    visual_challenge contributes its score to this weighted portion even though
    its `passed` boolean is checked separately as a must-pass check above.
    """
    present: Dict[str, float] = {}
    for key, weight in SIGNAL_WEIGHTS.items():
        result = signals.get(key)
        if result is not None and result.score is not None:
            present[key] = weight

    voice = signals.get("voice_authenticity")
    if voice is None:
        audio = signals.get("audio_pipeline")
        if audio is not None and audio.details:
            va_score = audio.details.get("voice_authenticity_score")
            if va_score is not None:
                present["voice_authenticity"] = SIGNAL_WEIGHTS["voice_authenticity"]

    av = signals.get("av_alignment")
    if av is None:
        audio = signals.get("audio_pipeline")
        if audio is not None and audio.details:
            av_score = audio.details.get("av_alignment_score")
            if av_score is not None:
                present["av_alignment"] = SIGNAL_WEIGHTS["av_alignment"]

    if not present:
        return None

    total_weight = sum(present.values())
    numerator = 0.0
    for key in present:
        if key == "voice_authenticity" and signals.get("voice_authenticity") is None:
            score = signals["audio_pipeline"].details["voice_authenticity_score"]
        elif key == "av_alignment" and signals.get("av_alignment") is None:
            score = signals["audio_pipeline"].details["av_alignment_score"]
        else:
            score = signals[key].score
        numerator += score * present[key]

    return numerator / total_weight


def evaluate(signals: Dict[str, DetectorResult]) -> FusionResult:
    """
    Run the must-pass checks first, then the weighted score.

    `signals` keys expected: visual_liveness, visual_challenge, deepfake, replay,
    audio_pipeline (the combined audio result). voice_authenticity and
    av_alignment may be read from audio_pipeline.details if not passed separately.
    """
    gate_reason = _must_pass_failed(signals)
    if gate_reason is not None:
        return FusionResult(status=VerificationStatus.FAILED, confidence=None, reason=gate_reason)

    score = _weighted_score(signals)
    if score is None:
        return FusionResult(
            status=VerificationStatus.FAILED,
            confidence=None,
            reason="All must-pass checks passed but no usable signal scores were available.",
        )

    if score >= VERIFIED_THRESHOLD:
        status = VerificationStatus.VERIFIED
    elif score >= SUSPICIOUS_THRESHOLD:
        status = VerificationStatus.SUSPICIOUS
    else:
        status = VerificationStatus.FAILED

    return FusionResult(
        status=status,
        confidence=round(score, 4),
        reason=f"Weighted signal score {score:.2f} against thresholds "
        f"(VERIFIED>={VERIFIED_THRESHOLD}, SUSPICIOUS>={SUSPICIOUS_THRESHOLD}).",
    )
