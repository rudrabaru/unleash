"""
Evidence Fusion + Decision Engine.

Interim policy (owner decision D-51), until a calibration campaign shows which signals separate
genuine people from attacks:

  * Must-pass checks decide first: the visual challenge and the audio speech and phrase checks. A
    failed one is FAILED; so is one that is missing (the check fails closed).
  * The score is the weighted average of the two signals that are calibrated enough to carry weight:
    visual liveness and the visual challenge's score.
  * Deepfake, replay, voice authenticity and lip sync still run and are shown with the result, but add
    nothing to the score and cannot veto it ("report-only"). They do not yet tell a genuine recording
    from a fake one.
  * Minimum coverage: VERIFIED needs both weighted signals to have a score. With one missing the
    verdict is capped at SUSPICIOUS (never raised, never turned into FAILED).

So VERIFIED means "the challenge was done in this recording": it is not a claim of protection against
deepfake, replay or synthetic-voice attacks (see the claims policy in CLAUDE.md).
"""
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.schemas.detector import DetectorResult
from app.schemas.session import VerificationStatus

# The signals that carry weight. Visual liveness 0.20 and the visual challenge's score 0.25, averaged
# over whichever of the two has a score (their ratio stays 4:5).
SIGNAL_WEIGHTS: Dict[str, float] = {
    "visual_liveness": 0.20,
    "visual_challenge": 0.25,
}

# Computed and reported, never scored. Promote one only when the calibration data allows it.
REPORT_ONLY_SIGNALS = ("deepfake", "replay", "voice_authenticity", "av_alignment")

VERIFIED_THRESHOLD = 0.80
SUSPICIOUS_THRESHOLD = 0.55


@dataclass
class FusionResult:
    status: VerificationStatus
    confidence: Optional[float]
    reason: str


def _must_pass_failed(signals: Dict[str, DetectorResult]) -> Optional[str]:
    """Return a human-readable reason if a must-pass check failed or is missing, else None."""
    visual_challenge = signals.get("visual_challenge")
    if visual_challenge is None:
        return "Visual challenge compliance failed: the check produced no result."
    if not visual_challenge.passed:
        return f"Visual challenge compliance failed: {visual_challenge.reason}"

    audio = signals.get("audio_pipeline")
    if audio is None:
        return "Audio must-pass check failed: the check produced no result."
    if not audio.passed:
        return f"Audio must-pass check failed: {audio.reason}"
    return None


def _scored(signals: Dict[str, DetectorResult]) -> Dict[str, float]:
    """The weighted signals that have a score, with their scores."""
    return {
        name: signals[name].score
        for name in SIGNAL_WEIGHTS
        if signals.get(name) is not None and signals[name].score is not None
    }


def _weighted_score(scores: Dict[str, float]) -> Optional[float]:
    """Weighted average of the scored signals, with the weight of a missing one shared by the rest (never as 0)."""
    if not scores:
        return None
    total_weight = sum(SIGNAL_WEIGHTS[name] for name in scores)
    return sum(score * SIGNAL_WEIGHTS[name] for name, score in scores.items()) / total_weight


def _band(score: float) -> VerificationStatus:
    if score >= VERIFIED_THRESHOLD:
        return VerificationStatus.VERIFIED
    if score >= SUSPICIOUS_THRESHOLD:
        return VerificationStatus.SUSPICIOUS
    return VerificationStatus.FAILED


def evaluate(signals: Dict[str, DetectorResult]) -> FusionResult:
    """
    Fuse the signals into a verdict: must-pass checks, then the weighted score, then the coverage cap.

    `signals` keys read: visual_liveness, visual_challenge and audio_pipeline. Deepfake, replay and the
    two advisory audio checks (reported inside audio_pipeline.details) are never read.
    """
    gate_reason = _must_pass_failed(signals)
    if gate_reason is not None:
        return FusionResult(status=VerificationStatus.FAILED, confidence=None, reason=gate_reason)

    scores = _scored(signals)
    score = _weighted_score(scores)
    if score is None:
        return FusionResult(
            status=VerificationStatus.FAILED,
            confidence=None,
            reason="All must-pass checks passed but no usable signal scores were available.",
        )

    status = _band(score)
    missing: List[str] = [name for name in SIGNAL_WEIGHTS if name not in scores]
    capped = bool(missing) and status == VerificationStatus.VERIFIED
    if capped:
        status = VerificationStatus.SUSPICIOUS

    reason = (
        f"Weighted score {score:.2f} from {', '.join(scores)} "
        f"(VERIFIED>={VERIFIED_THRESHOLD}, SUSPICIOUS>={SUSPICIOUS_THRESHOLD})."
    )
    if capped:
        reason += f" Capped at SUSPICIOUS because {', '.join(missing)} could not be measured."
    return FusionResult(status=status, confidence=round(score, 4), reason=reason)
