"""
Verification orchestrator.

`analyze_media` runs every detector on one recording and fuses the results; it is the single
entry point used by the session flow (`run_verification`, which also stores the decision) and
by the development-only `POST /api/v1/verify` demo. Failures are isolated per detector so one
broken module never takes the whole analysis down.
"""
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from app import db, fusion
from app.modules.audio import process_audio_pipeline
from app.modules.antispoof import detect_deepfake, detect_replay_attack
from app.modules.frame_extraction import extract_frames
from app.modules.visual import detect_visual_liveness, verify_challenge_compliance
from app.modules.visual._frames import extract_visual_frames
from app.modules.visual._landmarks import extract_landmark_features
from app.modules.visual._lip_series import build_lip_series
from app.schemas.detector import DetectorResult

logger = logging.getLogger("unleash.orchestrator")

# Signals that need video frames; they all fail together when the recording has none.
VIDEO_SIGNALS = ("visual_liveness", "visual_challenge", "deepfake", "replay")

# The speech detector keeps state between calls (`reset_states`) and the MediaPipe landmarker
# is created once and shared, so two analyses must not run at the same time. Analyses already
# run in worker threads (the detectors are plain blocking functions), so this lock is what
# serialises them.
_ANALYSIS_LOCK = threading.Lock()


@dataclass
class AnalysisResult:
    signals: Dict[str, DetectorResult]
    fusion: fusion.FusionResult
    timings: Dict[str, float] = field(default_factory=dict)


def _failed_result(reason: str, error: str) -> DetectorResult:
    return DetectorResult(score=None, passed=False, reason=reason, error=error)


def _safe_call(name: str, detector, *args, **kwargs) -> DetectorResult:
    """Never let one detector's exception take down the whole session."""
    try:
        return detector(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - a detector must never take the analysis down
        logger.exception("Detector %s raised", name)
        return _failed_result(reason="Detector unavailable", error=str(exc))


def _lip_series(landmark_features, fps: float):
    """Lip-openness series for the lip-sync check; optional, so any failure just omits it."""
    if landmark_features is None or landmark_features.get("error"):
        return None
    try:
        return build_lip_series(landmark_features, fps)
    except Exception:  # noqa: BLE001 - the lip-sync input is optional; never block the analysis
        logger.exception("Lip series build failed; the lip-sync check will degrade gracefully")
        return None


def analyze_media(media_path: Path, visual_challenge: str, verbal_challenge: str) -> AnalysisResult:
    with _ANALYSIS_LOCK:
        return _analyze(media_path, visual_challenge, verbal_challenge)


def _analyze(media_path: Path, visual_challenge: str, verbal_challenge: str) -> AnalysisResult:
    timings: Dict[str, float] = {}
    started = time.perf_counter()

    def timed(name: str, since: float) -> None:
        timings[name] = round(time.perf_counter() - since, 3)

    # ~30 evenly spaced frames for the deepfake and replay detectors.
    step = time.perf_counter()
    frame_result = extract_frames(str(media_path))
    frames = frame_result.frames
    # Dense, real-timestamped frames for the visual detectors (a blink lasts 0.1-0.3 s) and
    # for the lip series.
    visual_result = extract_visual_frames(media_path)
    visual_frames = visual_result.frames
    timed("frames", step)

    # MediaPipe runs once and the result is shared by liveness, challenge compliance and the
    # lip series instead of each re-running it over the same frames.
    step = time.perf_counter()
    landmark_features = None
    if visual_frames:
        try:
            landmark_features = extract_landmark_features(
                visual_frames,
                timestamps=visual_result.timestamps,
                original_indices=visual_result.original_indices,
            )
        except Exception:  # noqa: BLE001 - fall back to per-detector extraction
            logger.exception("Shared landmark extraction failed; detectors will each retry")
            landmark_features = None
    timed("landmarks", step)

    signals: Dict[str, DetectorResult] = {}

    step = time.perf_counter()
    signals["audio_pipeline"] = _safe_call(
        "audio_pipeline",
        process_audio_pipeline,
        str(media_path),
        verbal_challenge,
        lip_openness_data=_lip_series(landmark_features, visual_result.fps),
    )
    timed("audio", step)

    if frames or visual_frames:
        for name, detector, args, kwargs in (
            ("visual_liveness", detect_visual_liveness, (visual_frames,), {"features": landmark_features}),
            ("visual_challenge", verify_challenge_compliance, (visual_frames, visual_challenge), {"features": landmark_features}),
            ("deepfake", detect_deepfake, (frames,), {}),
            ("replay", detect_replay_attack, (frames,), {}),
        ):
            step = time.perf_counter()
            signals[name] = _safe_call(name, detector, *args, **kwargs)
            timed(name, step)
    else:
        error = frame_result.error or visual_result.error or "No video frames available."
        for name in VIDEO_SIGNALS:
            signals[name] = _failed_result(reason="No video frames available", error=error)

    step = time.perf_counter()
    result = fusion.evaluate(signals)
    timed("fusion", step)
    timed("total", started)
    return AnalysisResult(signals=signals, fusion=result, timings=timings)


def run_verification(session_id: str, media_path: Path, visual_challenge: str, verbal_challenge: str) -> None:
    analysis = analyze_media(media_path, visual_challenge, verbal_challenge)
    db.write_decision(
        session_id=session_id,
        status=analysis.fusion.status.value,
        confidence=analysis.fusion.confidence,
        decision_reason=analysis.fusion.reason,
        signals=analysis.signals,
        updated_at=datetime.now(timezone.utc),
    )
