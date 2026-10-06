"""
Speech check (voice-activity detection), the first must-pass audio check.

Uses silero-vad to confirm that human speech is present and that the speech lasts long enough
(>= 2.0 s) for a 5-word challenge response.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.modules.audio._constants import TARGET_SAMPLE_RATE
from app.modules.audio._io import read_wav_torch
from app.schemas.detector import DetectorResult

logger = logging.getLogger(__name__)

# A 5-word challenge takes about this long to say; less speech than this cannot be the phrase.
# Starting value, tunable once there are enough recorded takes (see the evaluation scenarios).
SPEECH_DURATION_THRESHOLD_S = 2.0

# silero-vad is loaded ONCE at import, never per request (loading takes seconds).
_VAD_MODEL: Optional[Any] = None
_VAD_BACKEND: str = "silero-vad"
_VAD_LOAD_ERROR: Optional[str] = None

try:
    from silero_vad import get_speech_timestamps, load_silero_vad
    _started = time.perf_counter()
    _VAD_MODEL = load_silero_vad()
    logger.info("silero-vad loaded in %.3fs", time.perf_counter() - _started)
except Exception as _exc:  # noqa: BLE001
    _VAD_LOAD_ERROR = f"{type(_exc).__name__}: {_exc}"
    logger.error("Failed to load silero-vad at import: %s", _VAD_LOAD_ERROR)


def _details(
    *,
    detected: bool = False,
    speech_seconds: float = 0.0,
    segments: Optional[List[Dict[str, float]]] = None,
    backend: Optional[str] = _VAD_BACKEND,
    **extra: Any,
) -> Dict[str, Any]:
    segments = segments or []
    return {
        "speech_detected": detected,
        "speech_duration_seconds": speech_seconds,
        "segment_count": len(segments),
        "segments": segments,
        "vad_backend": backend,
        **extra,
    }


def _failed(reason: str, error: Optional[str], backend: Optional[str] = _VAD_BACKEND, **extra: Any) -> DetectorResult:
    """No-speech, unreadable-input and internal-error results share one shape (score None, passed False)."""
    return DetectorResult(
        score=None, passed=False, reason=reason, error=error, details=_details(backend=backend, **extra)
    )


def _evaluate_speech_gate(speech_detected: bool, total_speech_s: float, segment_count: int) -> Tuple[bool, str]:
    """
    Evaluate the must-pass conditions for speech presence and minimum duration.
    Returns (passed, reason).
    """
    if not speech_detected:
        return False, "No speech detected in audio submission."

    if total_speech_s < SPEECH_DURATION_THRESHOLD_S:
        return False, (
            f"Speech duration ({total_speech_s:.2f}s) is below required minimum threshold "
            f"({SPEECH_DURATION_THRESHOLD_S:.1f}s) for a 5-word challenge response."
        )

    return True, (
        f"Speech detected: {total_speech_s:.2f}s across {segment_count} segments "
        f"(satisfies >= {SPEECH_DURATION_THRESHOLD_S:.1f}s threshold)."
    )


def _detect_speech(path: Path) -> DetectorResult:
    try:
        audio, file_duration = read_wav_torch(path)
    except Exception as e:  # noqa: BLE001 - unreadable audio is a result, not a crash
        return _failed(f"Failed to read WAV audio for VAD analysis: {e}", f"{type(e).__name__}: {e}")

    if len(audio) == 0 or file_duration <= 0:
        return DetectorResult(
            score=None, passed=False, reason="Audio file is empty (0 samples).", error=None,
            details=_details(file_duration_seconds=0.0),
        )

    _VAD_MODEL.reset_states()  # the model keeps state between calls
    segments: List[Dict[str, float]] = get_speech_timestamps(
        audio, _VAD_MODEL, sampling_rate=TARGET_SAMPLE_RATE, return_seconds=True
    )
    total_speech_s = round(sum(seg["end"] - seg["start"] for seg in segments), 3)
    passed, reason = _evaluate_speech_gate(len(segments) > 0, total_speech_s, len(segments))
    return DetectorResult(
        score=None,  # a must-pass check: it does not contribute a score
        passed=passed,
        reason=reason,
        error=None,
        details=_details(
            detected=len(segments) > 0,
            speech_seconds=total_speech_s,
            segments=segments,
            file_duration_seconds=round(file_duration, 3),
        ),
    )


def run_speech_gate(wav_path: Path | str) -> DetectorResult:
    """
    Run the speech check on a 16kHz mono WAV file.

    Passes only if speech is detected and lasts at least SPEECH_DURATION_THRESHOLD_S.
    Never raises; always returns a DetectorResult.
    """
    if _VAD_MODEL is None:
        return _failed(
            "Speech gate unavailable due to VAD model initialization error.",
            f"VAD backend not initialized: {_VAD_LOAD_ERROR or 'Unknown init error'}",
            backend=None,
        )

    try:
        path = Path(wav_path)
        if not path.exists():
            return _failed(f"Audio file not found: {path}", "Audio file does not exist")
        return _detect_speech(path)
    except Exception as e:  # noqa: BLE001 - a detector must never raise
        logger.exception("Unexpected error in run_speech_gate")
        return _failed(f"Speech check failed unexpectedly: {type(e).__name__}: {e}", f"{type(e).__name__}: {e}")
