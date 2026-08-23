"""
Stage 1: Speech Gate (VAD) Implementation.

Evaluates audio submissions using silero-vad to confirm the presence
of human speech and verify that speech duration is sufficient (>= 2.0s).
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import soundfile as sf
import torch

from app.schemas.detector import DetectorResult

logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000
SPEECH_DURATION_THRESHOLD_S = 2.0

# silero-vad loaded ONCE at module init (known-tricky-spots #1, #4)
_VAD_MODEL: Optional[Any] = None
_VAD_BACKEND: str = "silero-vad"
_VAD_LOAD_ERROR: Optional[str] = None
_VAD_LOAD_TIME_S: float = 0.0

try:
    _t0 = time.perf_counter()
    from silero_vad import get_speech_timestamps, load_silero_vad
    _VAD_MODEL = load_silero_vad()
    _VAD_LOAD_TIME_S = time.perf_counter() - _t0
    logger.info(f"silero-vad loaded successfully in {_VAD_LOAD_TIME_S:.3f}s")
except Exception as _e:  # noqa: BLE001
    _VAD_LOAD_ERROR = f"{type(_e).__name__}: {_e}"
    _VAD_MODEL = None
    logger.error(f"Failed to load silero-vad model at module init: {_VAD_LOAD_ERROR}")


def read_wav_16k(path: Path | str) -> Tuple[torch.Tensor, float]:
    """
    Read WAV audio using soundfile -> numpy float32 -> torch tensor.
    Guarantees float32 single-channel 16kHz tensor.
    Returns (audio_tensor, duration_seconds).
    """
    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if sr != TARGET_SAMPLE_RATE:
        raise ValueError(f"Expected sample rate {TARGET_SAMPLE_RATE}Hz, got {sr}Hz")
    if data.ndim > 1:
        data = np.mean(data, axis=1)
    
    duration = len(data) / float(sr) if sr > 0 else 0.0
    tensor = torch.from_numpy(np.ascontiguousarray(data))
    return tensor, duration


def run_speech_gate(wav_path: Path | str) -> DetectorResult:
    """
    Execute Stage 1 Speech Gate on a 16kHz mono WAV file.
    
    Hard gate requirements:
      - speech_detected == True
      - speech_duration >= 2.0s
    
    Guarantees:
      - Never raises an uncaught exception.
      - Returns a fully compliant DetectorResult.
      - Resets VAD model state prior to inference.
    """
    path_obj = Path(wav_path)

    # Check model initialization
    if _VAD_MODEL is None:
        err_msg = f"VAD backend not initialized: {_VAD_LOAD_ERROR or 'Unknown init error'}"
        return DetectorResult(
            score=None,
            passed=False,
            reason="Speech gate unavailable due to VAD model initialization error.",
            error=err_msg,
            details={
                "speech_detected": False,
                "speech_duration_seconds": 0.0,
                "segment_count": 0,
                "segments": [],
                "vad_backend": None
            }
        )

    # Check file existence
    if not path_obj.exists():
        return DetectorResult(
            score=None,
            passed=False,
            reason=f"Audio file not found: {path_obj}",
            error="Audio file does not exist",
            details={
                "speech_detected": False,
                "speech_duration_seconds": 0.0,
                "segment_count": 0,
                "segments": [],
                "vad_backend": _VAD_BACKEND
            }
        )

    try:
        # Load WAV file
        try:
            audio, file_duration = read_wav_16k(path_obj)
        except Exception as e:
            return DetectorResult(
                score=None,
                passed=False,
                reason=f"Failed to read WAV audio for VAD analysis: {e}",
                error=f"{type(e).__name__}: {e}",
                details={
                    "speech_detected": False,
                    "speech_duration_seconds": 0.0,
                    "segment_count": 0,
                    "segments": [],
                    "vad_backend": _VAD_BACKEND
                }
            )

        if len(audio) == 0 or file_duration <= 0:
            return DetectorResult(
                score=None,
                passed=False,
                reason="Audio file is empty (0 samples).",
                error=None,
                details={
                    "speech_detected": False,
                    "speech_duration_seconds": 0.0,
                    "segment_count": 0,
                    "segments": [],
                    "vad_backend": _VAD_BACKEND,
                    "file_duration_seconds": 0.0
                }
            )

        # Reset stateful singleton before every inference (Finding #5 / NOTES.md)
        _VAD_MODEL.reset_states()

        # Run VAD
        segments: List[Dict[str, float]] = get_speech_timestamps(
            audio,
            _VAD_MODEL,
            sampling_rate=TARGET_SAMPLE_RATE,
            return_seconds=True
        )

        total_speech_s = sum(seg["end"] - seg["start"] for seg in segments)
        total_speech_s = round(total_speech_s, 3)
        file_duration = round(file_duration, 3)
        speech_detected = len(segments) > 0

        # Hard Gate Logic:
        # 1. Must detect speech
        # 2. Total speech duration must be >= 2.0 seconds
        if not speech_detected:
            passed = False
            reason = "No speech detected in audio submission."
        elif total_speech_s < SPEECH_DURATION_THRESHOLD_S:
            passed = False
            reason = (
                f"Speech duration ({total_speech_s:.2f}s) is below required minimum threshold "
                f"({SPEECH_DURATION_THRESHOLD_S:.1f}s) for a 3-digit challenge response."
            )
        else:
            passed = True
            reason = (
                f"Speech detected: {total_speech_s:.2f}s across {len(segments)} segments "
                f"(satisfies >= {SPEECH_DURATION_THRESHOLD_S:.1f}s threshold)."
            )

        return DetectorResult(
            score=None,  # Stage 1 is a hard gate, does not set score
            passed=passed,
            reason=reason,
            error=None,
            details={
                "speech_detected": speech_detected,
                "speech_duration_seconds": total_speech_s,
                "segment_count": len(segments),
                "segments": segments,
                "vad_backend": _VAD_BACKEND,
                "file_duration_seconds": file_duration
            }
        )

    except Exception as e:
        logger.exception("Unexpected error in run_speech_gate")
        return DetectorResult(
            score=None,
            passed=False,
            reason=f"Stage 1 Speech Gate failed unexpectedly: {type(e).__name__}: {e}",
            error=f"{type(e).__name__}: {e}",
            details={
                "speech_detected": False,
                "speech_duration_seconds": 0.0,
                "segment_count": 0,
                "segments": [],
                "vad_backend": _VAD_BACKEND
            }
        )
