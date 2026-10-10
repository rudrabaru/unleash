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
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from app import db, fusion
from app.media.face_crop import crop_faces
from app.media.frames import DENSE_MAX_EDGE, load_frames
from app.modules.audio import process_audio_pipeline
from app.modules.antispoof import detect_deepfake, detect_replay_attack
from app.modules.visual import detect_visual_liveness, verify_challenge_compliance
from app.modules.visual._landmarks import extract_landmark_features
from app.modules.visual._lip_series import build_lip_series
from app.protocol import PROTOCOL_V1, PhaseWindows
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
    # The phase windows the analysis was given (None = judge the whole recording, as before).
    phases: Optional[PhaseWindows] = None


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


def warm_up() -> Dict[str, str]:
    """
    Load the models that are otherwise created on the first request (the audio models already
    load at import), so the first user does not wait for them. Returns an error text per model
    that could not be loaded; a failure here never stops the server, the detector reports it later.
    """
    from app.modules.antispoof._deepfake import classifier
    from app.modules.visual._landmarks import _get_landmarker

    failures: Dict[str, str] = {}
    for name, load in (("face_landmarker", _get_landmarker), ("deepfake", classifier._load_model)):
        try:
            load()
        except Exception as exc:  # noqa: BLE001 - a missing checkpoint must not block startup
            failures[name] = str(exc)
            logger.warning("Warm-up of %s failed: %s", name, exc)
    return failures


def analyze_media(
    media_path: Path,
    visual_challenge: str,
    verbal_challenge: str,
    phases: Optional[PhaseWindows] = None,
) -> AnalysisResult:
    """
    Analyse one recording. `phases` are the protocol windows (read, speak, act); with None every
    detector judges the whole recording as before. The visual and audio checks read them from here
    as they become phase-aware, so this is the one place a new window-dependent check hooks in.
    """
    with _ANALYSIS_LOCK:
        return _analyze(media_path, visual_challenge, verbal_challenge, phases)


def _shared_landmarks(bundle):
    """
    MediaPipe runs once and the result is shared by liveness, challenge compliance and the lip
    series instead of each re-running it over the same frames. None when it fails: the visual
    detectors then each retry on their own.
    """
    if not bundle.dense:
        return None
    try:
        return extract_landmark_features(
            bundle.dense,
            timestamps=bundle.dense_times,
            original_indices=bundle.dense_indices,
        )
    except Exception:  # noqa: BLE001 - fall back to per-detector extraction
        logger.exception("Shared landmark extraction failed; detectors will each retry")
        return None


def _run_video_detectors(bundle, landmark_features, visual_challenge: str, timer: "_Timer") -> Dict[str, DetectorResult]:
    if not (bundle.sparse or bundle.dense):
        error = bundle.error or "No video frames available."
        return {name: _failed_result(reason="No video frames available", error=error) for name in VIDEO_SIGNALS}

    # The deepfake classifier sees the face only: crops come from the shared landmarks.
    face_crops = crop_faces(bundle.sparse, bundle.sparse_indices, landmark_features)
    signals: Dict[str, DetectorResult] = {}
    for name, detector, args, kwargs in (
        ("visual_liveness", detect_visual_liveness, (bundle.dense,), {"features": landmark_features}),
        ("visual_challenge", verify_challenge_compliance, (bundle.dense, visual_challenge), {"features": landmark_features}),
        ("deepfake", detect_deepfake, (face_crops,), {}),
        ("replay", detect_replay_attack, (bundle.sparse,), {}),
    ):
        with timer.step(name):
            signals[name] = _safe_call(name, detector, *args, **kwargs)
    return signals


class _Timer:
    """Records how long each named step of one analysis takes, in seconds."""

    def __init__(self) -> None:
        self.timings: Dict[str, float] = {}
        self._started = time.perf_counter()

    @contextmanager
    def step(self, name: str):
        began = time.perf_counter()
        try:
            yield
        finally:
            self.timings[name] = round(time.perf_counter() - began, 3)

    def finish(self) -> Dict[str, float]:
        self.timings["total"] = round(time.perf_counter() - self._started, 3)
        return self.timings


def _analyze(
    media_path: Path,
    visual_challenge: str,
    verbal_challenge: str,
    phases: Optional[PhaseWindows],
) -> AnalysisResult:
    timer = _Timer()

    # One decode gives ~120 timestamped frames for the visual detectors (a blink lasts 0.1-0.3 s)
    # and the lip series, and ~30 native-resolution frames (a subset) for deepfake and replay.
    with timer.step("frames"):
        bundle = load_frames(media_path, dense_max_edge=DENSE_MAX_EDGE)
    with timer.step("landmarks"):
        landmark_features = _shared_landmarks(bundle)

    signals: Dict[str, DetectorResult] = {}
    with timer.step("audio"):
        signals["audio_pipeline"] = _safe_call(
            "audio_pipeline",
            process_audio_pipeline,
            str(media_path),
            verbal_challenge,
            lip_openness_data=_lip_series(landmark_features, bundle.fps),
        )
    signals.update(_run_video_detectors(bundle, landmark_features, visual_challenge, timer))

    with timer.step("fusion"):
        result = fusion.evaluate(signals)
    return AnalysisResult(signals=signals, fusion=result, timings=timer.finish(), phases=phases)


def run_verification(session_id: str, media_path: Path, visual_challenge: str, verbal_challenge: str) -> None:
    analysis = analyze_media(media_path, visual_challenge, verbal_challenge, phases=PROTOCOL_V1)
    db.write_decision(
        session_id=session_id,
        status=analysis.fusion.status.value,
        confidence=analysis.fusion.confidence,
        decision_reason=analysis.fusion.reason,
        signals=analysis.signals,
        updated_at=datetime.now(timezone.utc),
    )
