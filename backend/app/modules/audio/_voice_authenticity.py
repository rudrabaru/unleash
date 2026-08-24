"""
Stage 3: Voice Authenticity (Spectral Heuristics) Implementation.

Evaluates audio authenticity via spectral heuristics to flag TTS audio injection
and physical speaker replay. Computes an advisory score (0.0 - 1.0) based on:
1. Noise floor consistency across silence intervals
2. Spectral flux variance across voiced speech segments
3. High-frequency energy rolloff ratio

Note: Stage 3 is purely advisory and never hard-gates the verification session.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.modules.audio._io import read_wav_numpy
from app.schemas.detector import DetectorResult

# Backward compatibility alias
read_audio_for_analysis = read_wav_numpy

logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000

# Composite weights (must sum to 1.0)
NOISE_WEIGHT = 0.30
FLUX_WEIGHT = 0.45
HF_RATIO_WEIGHT = 0.25

# librosa loaded at module init with graceful fallback
_LIBROSA_AVAILABLE: bool = False
_LIBROSA_LOAD_ERROR: Optional[str] = None
try:
    import librosa
    _LIBROSA_AVAILABLE = True
except Exception as _e:  # noqa: BLE001
    _LIBROSA_LOAD_ERROR = f"{type(_e).__name__}: {_e}"
    librosa = None  # type: ignore
    logger.warning(f"librosa import failed at module init: {_LIBROSA_LOAD_ERROR}")


def compute_noise_floor_score(
    audio: np.ndarray,
    sr: int,
    speech_segments: List[Dict[str, float]],
    total_duration: float
) -> Tuple[float, Dict[str, Any]]:
    """
    Heuristic 1: Noise floor consistency.
    Analyzes silence/inter-speech regions for natural sensor noise vs. artificial digital silence.
    
    Live microphone speech contains subtle, non-zero acoustic/sensor noise with natural variance.
    Pure TTS / synthetic injection often exhibits absolute digital silence or flat zeros between words.
    """
    if len(audio) == 0 or total_duration <= 0:
        return 0.5, {"mean_rms": 0.0, "cov": 0.0, "silence_samples": 0}

    # Extract non-speech / silence slices sorted by start time
    sorted_segs = sorted(speech_segments, key=lambda s: s.get("start", 0.0))
    silence_slices: List[np.ndarray] = []
    
    prev_end = 0.0
    for seg in sorted_segs:
        start = max(0.0, seg.get("start", 0.0))
        end = max(start, seg.get("end", start))
        # Silence gap between prev_end and start
        if start - prev_end >= 0.05:  # At least 50ms gap
            start_idx = int(prev_end * sr)
            end_idx = int(start * sr)
            if end_idx > start_idx:
                silence_slices.append(audio[start_idx:end_idx])
        prev_end = end

    # Tail silence
    if total_duration - prev_end >= 0.05:
        start_idx = int(prev_end * sr)
        end_idx = min(len(audio), int(total_duration * sr))
        if end_idx > start_idx:
            silence_slices.append(audio[start_idx:end_idx])

    if not silence_slices:
        # No detectable silence gaps (all speech) - return neutral score
        return 0.5, {"mean_rms": 0.0, "cov": 0.0, "silence_samples": 0}

    silence_audio = np.concatenate(silence_slices)
    if len(silence_audio) < int(0.05 * sr):  # < 50ms total silence
        return 0.5, {"mean_rms": 0.0, "cov": 0.0, "silence_samples": len(silence_audio)}

    # Compute short-term RMS in windows of 256 samples (~16ms at 16kHz)
    window_size = 256
    hop_size = 128
    num_frames = (len(silence_audio) - window_size) // hop_size + 1
    if num_frames <= 1:
        rms_values = np.array([np.sqrt(np.mean(silence_audio ** 2) + 1e-12)])
    else:
        shape = (num_frames, window_size)
        strides = (silence_audio.strides[0] * hop_size, silence_audio.strides[0])
        frames = np.lib.stride_tricks.as_strided(silence_audio, shape=shape, strides=strides)
        rms_values = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)

    mean_rms = float(np.mean(rms_values))
    std_rms = float(np.std(rms_values))
    cov = std_rms / (mean_rms + 1e-9)

    # Scoring evaluation:
    # 1. Suspiciously zero digital noise (mean_rms < 1e-5) -> low score
    if mean_rms < 1e-5:
        score = 0.1
    # 2. Perfectly flat constant noise floor (cov < 0.05) -> low score
    elif cov < 0.05:
        score = 0.2
    else:
        # Natural noise floor: scale smoothly with healthy CoV and non-zero mean RMS
        cov_norm = min(cov / 0.15, 1.0)
        rms_norm = min(mean_rms / 1e-3, 1.0)
        score = float(0.2 + 0.8 * (0.6 * cov_norm + 0.4 * rms_norm))

    score = min(max(score, 0.0), 1.0)
    return round(score, 3), {
        "mean_rms": round(mean_rms, 6),
        "std_rms": round(std_rms, 6),
        "cov": round(cov, 4),
        "silence_samples": len(silence_audio)
    }


def compute_spectral_flux_score(
    speech_audio: np.ndarray,
    sr: int
) -> Tuple[float, Dict[str, Any]]:
    """
    Heuristic 2: Spectral flux variance across speech segments.
    Measures frame-to-frame spectral variation. Live human vocal tract dynamics
    produce natural spectral fluctuations, whereas synthetic TTS models often exhibit
    overly uniform or rigid spectral transitions.
    """
    if len(speech_audio) < 512 or not _LIBROSA_AVAILABLE or librosa is None:
        return 0.5, {"std_flux": 0.0, "mean_flux": 0.0}

    # Compute magnitude STFT
    n_fft = 512
    hop_length = 128
    D = librosa.stft(speech_audio, n_fft=n_fft, hop_length=hop_length)
    mag = np.abs(D)

    if mag.shape[1] < 2:
        return 0.5, {"std_flux": 0.0, "mean_flux": 0.0}

    # Half-wave rectified / L1 spectral flux
    flux = np.sum(np.maximum(0.0, mag[:, 1:] - mag[:, :-1]), axis=0)
    std_flux = float(np.std(flux))
    mean_flux = float(np.mean(flux))

    # Scale score against calibration target (target ~8.0 - 12.0 std flux)
    score = min(max(std_flux / 10.0, 0.0), 1.0)

    return round(score, 3), {
        "std_flux": round(std_flux, 4),
        "mean_flux": round(mean_flux, 4),
        "num_frames": int(mag.shape[1])
    }


def compute_hf_rolloff_score(
    speech_audio: np.ndarray,
    sr: int
) -> Tuple[float, Dict[str, Any]]:
    """
    Heuristic 3: High-frequency rolloff ratio.
    Compares energy in upper acoustic frequencies (>4kHz) to lower formant frequencies (0-4kHz).
    Physical speaker playback often exhibits steep frequency drop-offs above 4-6kHz.
    """
    if len(speech_audio) < 512 or not _LIBROSA_AVAILABLE or librosa is None:
        return 0.5, {"hf_ratio": 0.0, "high_band_energy": 0.0, "low_band_energy": 0.0}

    n_mels = 128
    mel_spec = librosa.feature.melspectrogram(
        y=speech_audio,
        sr=sr,
        n_fft=512,
        hop_length=128,
        n_mels=n_mels,
        fmax=8000
    )

    # Bands 0-79: 0 to ~4000Hz; Bands 80-127: ~4000Hz to 8000Hz
    low_band = mel_spec[:80, :]
    high_band = mel_spec[80:, :]

    low_energy = float(np.mean(low_band))
    high_energy = float(np.mean(high_band))
    hf_ratio = high_energy / (low_energy + 1e-10)

    # Replay through small phone/laptop speakers exhibits hf_ratio < 0.03
    # Healthy live speech into direct mic typically exhibits hf_ratio in 0.08 - 0.25+
    score = min(max(hf_ratio / 0.15, 0.0), 1.0)

    return round(score, 3), {
        "hf_ratio": round(hf_ratio, 4),
        "low_energy": round(low_energy, 6),
        "high_energy": round(high_energy, 6)
    }


def _extract_speech_audio(
    audio: np.ndarray,
    sr: int,
    speech_segments: List[Dict[str, float]]
) -> np.ndarray:
    """Extract and concatenate speech audio segments according to VAD boundaries."""
    speech_slices: List[np.ndarray] = []
    for seg in speech_segments:
        st = max(0.0, seg.get("start", 0.0))
        en = max(st, seg.get("end", st))
        st_idx = int(st * sr)
        en_idx = min(len(audio), int(en * sr))
        if en_idx > st_idx:
            speech_slices.append(audio[st_idx:en_idx])

    if speech_slices:
        return np.concatenate(speech_slices)
    return audio


def _compute_composite_score(noise_score: float, flux_score: float, hf_score: float) -> float:
    """Compute weighted composite score across all heuristics."""
    composite = (
        noise_score * NOISE_WEIGHT +
        flux_score * FLUX_WEIGHT +
        hf_score * HF_RATIO_WEIGHT
    )
    return round(min(max(composite, 0.0), 1.0), 3)


def _build_advisory_error_result(
    reason: str,
    error: Optional[str],
    segments_count: int = 0,
    elapsed: float = 0.0
) -> DetectorResult:
    """Construct an advisory DetectorResult for error scenarios (passed=True, score=None)."""
    return DetectorResult(
        score=None,
        passed=True,  # Advisory only: never hard-fail session
        reason=reason,
        error=error,
        details={
            "voice_authenticity_score": None,
            "noise_floor_score": None,
            "spectral_flux_score": None,
            "hf_ratio_score": None,
            "speech_segments_analysed": segments_count,
            "analysis_duration_seconds": elapsed
        }
    )


def _build_advisory_success_result(
    voice_authenticity_score: float,
    noise_score: float,
    flux_score: float,
    hf_score: float,
    segments_count: int,
    elapsed: float,
    noise_meta: Dict[str, Any],
    flux_meta: Dict[str, Any],
    hf_meta: Dict[str, Any]
) -> DetectorResult:
    """Construct an advisory DetectorResult for successful spectral analysis."""
    reason = (
        f"Voice authenticity score: {voice_authenticity_score:.3f} "
        f"(noise_floor={noise_score:.3f}, spectral_flux={flux_score:.3f}, hf_ratio={hf_score:.3f})."
    )
    return DetectorResult(
        score=voice_authenticity_score,
        passed=True,  # Advisory only
        reason=reason,
        error=None,
        details={
            "voice_authenticity_score": voice_authenticity_score,
            "noise_floor_score": noise_score,
            "spectral_flux_score": flux_score,
            "hf_ratio_score": hf_score,
            "speech_segments_analysed": segments_count,
            "heuristic_weights": {
                "noise": NOISE_WEIGHT,
                "flux": FLUX_WEIGHT,
                "hf_ratio": HF_RATIO_WEIGHT
            },
            "analysis_duration_seconds": elapsed,
            "metrics": {
                "noise": noise_meta,
                "flux": flux_meta,
                "hf": hf_meta
            }
        }
    )


def run_voice_authenticity(
    wav_path: Path | str,
    speech_segments: Optional[List[Dict[str, float]]] = None
) -> DetectorResult:
    """
    Execute Stage 3 Voice Authenticity analysis on a 16kHz mono WAV file.
    
    Guarantees:
    - Never raises an uncaught exception.
    - Always adheres to the 4-key DetectorResult contract.
    - Stage 3 is advisory: returns passed=True on standard evaluation,
      or passed=True with score=None and error populated on unexpected execution failure.
    """
    t_start = time.perf_counter()
    path_obj = Path(wav_path)

    if not path_obj.exists():
        return _build_advisory_error_result(
            reason=f"Audio file not found for voice authenticity analysis: {path_obj}",
            error="Audio file does not exist",
            segments_count=0
        )

    try:
        audio, sr, duration = read_wav_numpy(path_obj)
        if len(audio) == 0:
            return _build_advisory_error_result(
                reason="Audio file is empty for voice authenticity analysis.",
                error="Empty audio file",
                segments_count=0
            )

        segments = speech_segments or []
        speech_audio = _extract_speech_audio(audio, sr, segments)

        # 1. Noise Floor Consistency
        noise_score, noise_meta = compute_noise_floor_score(audio, sr, segments, duration)

        # 2. Spectral Flux Variance
        flux_score, flux_meta = compute_spectral_flux_score(speech_audio, sr)

        # 3. High-Frequency Rolloff Ratio
        hf_score, hf_meta = compute_hf_rolloff_score(speech_audio, sr)

        # 4. Composite Scoring
        voice_authenticity_score = _compute_composite_score(noise_score, flux_score, hf_score)
        elapsed = round(time.perf_counter() - t_start, 3)

        return _build_advisory_success_result(
            voice_authenticity_score=voice_authenticity_score,
            noise_score=noise_score,
            flux_score=flux_score,
            hf_score=hf_score,
            segments_count=len(segments),
            elapsed=elapsed,
            noise_meta=noise_meta,
            flux_meta=flux_meta,
            hf_meta=hf_meta
        )

    except Exception as e:
        logger.exception("Unexpected error in run_voice_authenticity")
        elapsed = round(time.perf_counter() - t_start, 3)
        return _build_advisory_error_result(
            reason=f"Voice authenticity analysis encountered unexpected error: {type(e).__name__}: {e}",
            error=f"{type(e).__name__}: {e}",
            segments_count=len(speech_segments) if speech_segments else 0,
            elapsed=elapsed
        )
