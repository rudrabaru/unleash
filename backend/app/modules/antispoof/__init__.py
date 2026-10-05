"""
Anti-Spoofing Detection Module (Owned by Dev 3)
- Module 1: Deepfake Detector (self-trained Xception, CPU-only)
- Module 2: Replay Detector (OpenCV FFT moiré + temporal noise + brightness histogram)
"""
from app.schemas.detector import DetectorResult
from app.modules.antispoof._deepfake import ModelNotReadyError, classifier
from app.modules.antispoof._replay import REPLAY_PASS_THRESHOLD, score_replay


def detect_deepfake(frames: list) -> DetectorResult:
    """
    Self-trained Xception deepfake classifier, forced to CPU.

    No trained checkpoint ships with this repo yet (Phase 3 blocker: requires
    a FaceForensics++-style dataset to train on). Until UNLEASH_XCEPTION_CHECKPOINT
    points at a real file, this returns an honest null-score error result — never
    a fabricated pass/fail (J5).
    """
    if not frames:
        return DetectorResult(score=None, passed=False, reason="No video frames available.", error="empty frame list")

    try:
        prediction, confidence, frame_probabilities = classifier.predict_video(frames)
    except ModelNotReadyError as exc:
        return DetectorResult(score=None, passed=False, reason="Deepfake detector could not produce a score.", error=str(exc))
    except Exception as exc:  # noqa: BLE001 - a detector must never raise
        return DetectorResult(score=None, passed=False, reason="Deepfake detection failed.", error=str(exc))

    fake_probability = confidence if prediction == "FAKE" else 1.0 - confidence
    real_score = 1.0 - fake_probability
    passed = prediction == "REAL"

    return DetectorResult(
        score=round(real_score, 4),
        passed=passed,
        reason=f"Video classified as {prediction} from {len(frame_probabilities)} sampled frames.",
        error=None,
        details={
            "prediction": prediction,
            "confidence": round(confidence, 4),
            "processed_frames": len(frame_probabilities),
            "fake_probability": round(fake_probability, 4),
        },
    )


def detect_replay_attack(frames: list) -> DetectorResult:
    """
    Replay Screen Attack Detector (Phase 4): FFT moire (55%) + temporal noise std (30%) +
    brightness histogram shape (15%), pass threshold 0.60. See `_replay.py` for the
    per-signal design and its honest [UNCALIBRATED] status.
    """
    if not frames:
        return DetectorResult(score=None, passed=False, reason="No video frames available.", error="empty frame list")

    try:
        result = score_replay(frames)
    except Exception as exc:  # noqa: BLE001 - a detector must never raise
        return DetectorResult(score=None, passed=False, reason="Replay detection failed.", error=str(exc))

    if result["score"] is None:
        return DetectorResult(
            score=None,
            passed=False,
            reason="Replay detector could not measure any sub-signal.",
            error=result.get("degraded_reason", "no measurable replay signal"),
        )

    def _fmt(value):
        return "n/a" if value is None else f"{value:.2f}"

    reason = (
        f"Replay score {result['score']:.2f} "
        f"(moire={_fmt(result['moire']['score'])}, noise={_fmt(result['temporal_noise']['score'])}, "
        f"brightness={_fmt(result['brightness_histogram']['score'])}) against pass threshold "
        f"{REPLAY_PASS_THRESHOLD:.2f}."
    )

    return DetectorResult(
        score=result["score"],
        passed=result["passed"],
        reason=reason,
        error=None,
        details={
            "moire_score": result["moire"]["score"],
            "moire_frames_sampled": result["moire"]["frames_sampled"],
            "noise_score": result["temporal_noise"]["score"],
            "mean_frame_diff_std": result["temporal_noise"]["mean_diff_std"],
            "brightness_score": result["brightness_histogram"]["score"],
            "brightness_entropy_bits": result["brightness_histogram"]["entropy_bits"],
            "brightness_clip_fraction": result["brightness_histogram"]["clip_fraction"],
            "frames_analyzed": result["frames_analyzed"],
            "calibration": "uncalibrated",
        }
    )
