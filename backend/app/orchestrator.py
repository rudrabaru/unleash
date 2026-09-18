"""
Verification Orchestrator.

Called from the BackgroundTasks submit flow. Extracts frames once, calls all five
detector modules, isolates per-module failures, runs fusion, and persists the
decision. Per docs/unleash_team_companion_guide.md Section 2.5.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from app import db, fusion
from app.modules.audio import process_audio_pipeline
from app.modules.antispoof import detect_deepfake, detect_replay_attack
from app.modules.frame_extraction import extract_frames
from app.modules.visual import detect_visual_liveness, verify_challenge_compliance
from app.modules.visual._landmarks import extract_landmark_features
from app.modules.visual._lip_series import build_lip_series
from app.schemas.detector import DetectorResult

logger = logging.getLogger("unleash.orchestrator")


def _failed_result(reason: str, error: str) -> DetectorResult:
    return DetectorResult(score=None, passed=False, reason=reason, error=error)


async def _safe_call(name: str, coro) -> DetectorResult:
    """Never let one detector's exception take down the whole session."""
    try:
        return await coro
    except Exception as exc:  # noqa: BLE001 - per plan's graceful-failure contract
        logger.exception("Detector %s raised", name)
        return _failed_result(reason="Detector unavailable", error=str(exc))


async def run_verification(session_id: str, media_path: Path, visual_challenge: str, verbal_challenge: str) -> None:
    signals: Dict[str, DetectorResult] = {}

    frame_result = extract_frames(str(media_path))
    frames = frame_result.frames

    # Run MediaPipe landmark extraction once per session and share the result across
    # liveness, challenge compliance, and the Stage 4 lip series instead of each of the
    # three re-running it independently over the same frame list.
    landmark_features = None
    if frames:
        try:
            landmark_features = extract_landmark_features(frames)
        except Exception:  # noqa: BLE001 - fall back to per-consumer extraction below
            logger.exception("Shared landmark extraction failed; consumers will each retry")
            landmark_features = None

    lip_openness_data = None
    if landmark_features is not None and not landmark_features.get("error"):
        try:
            lip_openness_data = build_lip_series(landmark_features, frame_result.fps)
        except Exception:  # noqa: BLE001 - Stage 4 input is optional; never block the pipeline
            logger.exception("Lip series build failed; Stage 4 will degrade gracefully")

    signals["audio_pipeline"] = await _safe_call(
        "audio_pipeline",
        process_audio_pipeline(str(media_path), verbal_challenge, lip_openness_data=lip_openness_data),
    )
    signals["visual_liveness"] = await _safe_call(
        "visual_liveness", detect_visual_liveness(frames, features=landmark_features)
    )
    signals["visual_challenge"] = await _safe_call(
        "visual_challenge", verify_challenge_compliance(frames, visual_challenge, features=landmark_features)
    )
    signals["deepfake"] = await _safe_call("deepfake", detect_deepfake(frames))
    signals["replay"] = await _safe_call("replay", detect_replay_attack(frames))

    if frame_result.error:
        for key in ("visual_liveness", "visual_challenge", "deepfake", "replay"):
            if signals[key].error is None and not frames:
                signals[key] = _failed_result(
                    reason="No video frames available", error=frame_result.error
                )

    result = fusion.evaluate(signals)
    now = datetime.now(timezone.utc)
    db.write_decision(
        session_id=session_id,
        status=result.status.value,
        confidence=result.confidence,
        decision_reason=result.reason,
        signals=signals,
        updated_at=now,
    )
