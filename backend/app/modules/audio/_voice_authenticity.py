"""
Voice authenticity check (spectral heuristics), an advisory audio check.

Evaluates audio authenticity via spectral heuristics to flag TTS audio injection
and physical speaker replay. Computes an advisory score (0.0 - 1.0) based on:
1. Noise floor consistency across silence intervals
2. Spectral flux variance across voiced speech segments
3. High-frequency energy rolloff ratio

It is purely advisory and never fails the verification session.

CALIBRATION STATUS: [UNCALIBRATED]. The heuristics below are real computations on real audio --
nothing here is stubbed -- but every threshold, divisor and weight is an initial guess that has
never been fitted to a labelled recording set. Measured against the only labelled recordings
that were available (2 genuine, 1 TTS), the composite produced NO separation between genuine
and TTS speech, the spectral-flux term saturated to 1.0 on all of them, and the HF-rolloff term
ran opposite to its documented direction. Treat the score as unvalidated until a labelled set of
genuine, replayed and synthetic recordings exists.

A sub-heuristic that cannot perform a real measurement returns score None and flags
details["voice_degraded"]=True with a reason; the composite uses only the heuristics that
measured (weights renormalized). If none measured, the check returns score None with an error.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.modules.audio._io import read_wav_numpy
from app.schemas.detector import DetectorResult

logger = logging.getLogger(__name__)

# Composite weights (must sum to 1.0)
# CALIBRATION STATUS: uncalibrated. These weights, and every divisor/bucket constant below,
# are initial guesses that have never been fitted to a labelled recording set; they currently
# produce no genuine-vs-TTS separation. Do not cite them as tuned values.
NOISE_WEIGHT = 0.30
FLUX_WEIGHT = 0.45
HF_RATIO_WEIGHT = 0.25

# Minimum samples required for a 512-point STFT frame.
MIN_STFT_SAMPLES = 512

# librosa is loaded at import with a graceful fallback. One STFT is run at import to remove
# the ~4 s first-call penalty from the first request.
_LIBROSA_AVAILABLE: bool = False
_LIBROSA_LOAD_ERROR: Optional[str] = None
try:
    import librosa
    librosa.stft(np.zeros(512, dtype=np.float32), n_fft=512, hop_length=128)
    _LIBROSA_AVAILABLE = True
    logger.info("librosa loaded and warmed up successfully")
except Exception as _exc:  # noqa: BLE001
    _LIBROSA_LOAD_ERROR = f"{type(_exc).__name__}: {_exc}"
    librosa = None  # type: ignore
    logger.warning("librosa import failed at import: %s", _LIBROSA_LOAD_ERROR)


def _degraded_meta(reason: str, **extra: Any) -> Dict[str, Any]:
    """
    Build a metrics dict for a fallback branch that did NOT perform a real measurement.

    The sub-heuristic's score is None on these branches (never a placeholder number); the
    composite is computed from the heuristics that did measure, and flagging it here keeps
    the persisted telemetry honest about which ones did.
    """
    meta: Dict[str, Any] = {"degraded": True, "degraded_reason": reason}
    meta.update(extra)
    return meta


def _measured_meta(**values: Any) -> Dict[str, Any]:
    """Build a metrics dict for a branch that did perform a real measurement."""
    meta: Dict[str, Any] = {"degraded": False, "degraded_reason": None}
    meta.update(values)
    return meta


def _collect_degradations(*metas: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Aggregate per-heuristic degradation flags into one overall flag plus its reasons."""
    reasons = [
        str(m.get("degraded_reason"))
        for m in metas
        if m.get("degraded") and m.get("degraded_reason")
    ]
    return bool(reasons), reasons


MIN_SILENCE_GAP_S = 0.05  # silence shorter than this is too short to measure a noise floor


def _silence_audio(
    audio: np.ndarray, sr: int, speech_segments: List[Dict[str, float]], total_duration: float
) -> np.ndarray:
    """Concatenate the non-speech gaps (before, between and after the speech segments)."""
    slices: List[np.ndarray] = []
    previous_end = 0.0
    for seg in sorted(speech_segments, key=lambda x: x.get("start", 0.0)):
        start = max(0.0, seg.get("start", 0.0))
        end = max(start, seg.get("end", start))
        if start - previous_end >= MIN_SILENCE_GAP_S:
            start_idx, end_idx = int(previous_end * sr), int(start * sr)
            if end_idx > start_idx:
                slices.append(audio[start_idx:end_idx])
        previous_end = end

    if total_duration - previous_end >= MIN_SILENCE_GAP_S:  # tail silence
        start_idx, end_idx = int(previous_end * sr), min(len(audio), int(total_duration * sr))
        if end_idx > start_idx:
            slices.append(audio[start_idx:end_idx])
    return np.concatenate(slices) if slices else np.array([], dtype=audio.dtype)


def _rms_values(silence_audio: np.ndarray) -> np.ndarray:
    """Short-term RMS in windows of 256 samples (~16 ms at 16 kHz), hop 128."""
    window_size, hop_size = 256, 128
    num_frames = (len(silence_audio) - window_size) // hop_size + 1
    if num_frames <= 1:
        return np.array([np.sqrt(np.mean(silence_audio ** 2) + 1e-12)])
    shape = (num_frames, window_size)
    strides = (silence_audio.strides[0] * hop_size, silence_audio.strides[0])
    frames = np.lib.stride_tricks.as_strided(silence_audio, shape=shape, strides=strides)
    return np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)


def _noise_floor_points(mean_rms: float, cov: float) -> float:
    """UNCALIBRATED mapping from the measured noise floor to a 0-1 score."""
    if mean_rms < 1e-5:  # suspiciously zero digital noise
        return 0.1
    if cov < 0.05:  # perfectly flat constant noise floor
        return 0.2
    # Natural noise floor: scale smoothly with a healthy coefficient of variation and non-zero RMS
    cov_norm = min(cov / 0.15, 1.0)
    rms_norm = min(mean_rms / 1e-3, 1.0)
    return float(0.2 + 0.8 * (0.6 * cov_norm + 0.4 * rms_norm))


def compute_noise_floor_score(
    audio: np.ndarray,
    sr: int,
    speech_segments: List[Dict[str, float]],
    total_duration: float
) -> Tuple[Optional[float], Dict[str, Any]]:
    """
    Heuristic 1: Noise floor consistency.
    Analyzes silence/inter-speech regions for natural sensor noise vs. artificial digital silence.

    Live microphone speech contains subtle, non-zero acoustic/sensor noise with natural variance.
    Pure TTS / synthetic injection often exhibits absolute digital silence or flat zeros between words.
    """
    if len(audio) == 0 or total_duration <= 0:
        return None, _degraded_meta("no audio to measure a noise floor from", mean_rms=0.0, cov=0.0, silence_samples=0)

    silence_audio = _silence_audio(audio, sr, speech_segments, total_duration)
    if len(silence_audio) == 0:
        return None, _degraded_meta(
            "no inter-speech silence gaps found (>=50ms) to measure a noise floor",
            mean_rms=0.0, cov=0.0, silence_samples=0
        )
    if len(silence_audio) < int(MIN_SILENCE_GAP_S * sr):
        return None, _degraded_meta(
            "total inter-speech silence under 50ms; too short to measure a noise floor",
            mean_rms=0.0, cov=0.0, silence_samples=len(silence_audio)
        )

    rms_values = _rms_values(silence_audio)
    mean_rms = float(np.mean(rms_values))
    std_rms = float(np.std(rms_values))
    cov = std_rms / (mean_rms + 1e-9)
    score = min(max(_noise_floor_points(mean_rms, cov), 0.0), 1.0)
    return round(score, 3), _measured_meta(
        mean_rms=round(mean_rms, 6),
        std_rms=round(std_rms, 6),
        cov=round(cov, 4),
        silence_samples=len(silence_audio)
    )


def compute_spectral_flux_score(
    speech_audio: np.ndarray,
    sr: int
) -> Tuple[Optional[float], Dict[str, Any]]:
    """
    Heuristic 2: Spectral flux variance across speech segments.
    Measures frame-to-frame spectral variation. Live human vocal tract dynamics
    produce natural spectral fluctuations, whereas synthetic TTS models often exhibit
    overly uniform or rigid spectral transitions.
    """
    if not _LIBROSA_AVAILABLE or librosa is None:
        return None, _degraded_meta(
            f"librosa unavailable, spectral flux not computed ({_LIBROSA_LOAD_ERROR})",
            std_flux=0.0, mean_flux=0.0
        )

    if len(speech_audio) < MIN_STFT_SAMPLES:
        return None, _degraded_meta(
            f"speech audio shorter than one {MIN_STFT_SAMPLES}-sample STFT frame",
            std_flux=0.0, mean_flux=0.0
        )

    # Compute magnitude STFT
    n_fft = 512
    hop_length = 128
    D = librosa.stft(speech_audio, n_fft=n_fft, hop_length=hop_length)
    mag = np.abs(D)

    if mag.shape[1] < 2:
        return None, _degraded_meta(
            "fewer than 2 STFT frames; frame-to-frame flux undefined",
            std_flux=0.0, mean_flux=0.0
        )

    # Half-wave rectified / L1 spectral flux
    flux = np.sum(np.maximum(0.0, mag[:, 1:] - mag[:, :-1]), axis=0)
    std_flux = float(np.std(flux))
    mean_flux = float(np.mean(flux))

    # Scaled with divisor 20.0 so natural std_flux (8.6-16.6) provides dynamic range
    # across recordings rather than always saturating to 1.0 (BUG-11 fix).
    FLUX_DIVISOR = 20.0
    score = min(max(std_flux / FLUX_DIVISOR, 0.0), 1.0)

    return round(score, 3), _measured_meta(
        std_flux=round(std_flux, 4),
        mean_flux=round(mean_flux, 4),
        num_frames=int(mag.shape[1]),
        saturated=bool(std_flux >= FLUX_DIVISOR)
    )


def compute_hf_rolloff_score(
    speech_audio: np.ndarray,
    sr: int
) -> Tuple[Optional[float], Dict[str, Any]]:
    """
    Heuristic 3: High-frequency rolloff ratio.
    Compares energy in upper acoustic frequencies (>4kHz) to lower formant frequencies (0-4kHz).
    Physical speaker playback often exhibits steep frequency drop-offs above 4-6kHz.
    """
    if not _LIBROSA_AVAILABLE or librosa is None:
        return None, _degraded_meta(
            f"librosa unavailable, HF rolloff not computed ({_LIBROSA_LOAD_ERROR})",
            hf_ratio=0.0, low_energy=0.0, high_energy=0.0
        )

    if len(speech_audio) < MIN_STFT_SAMPLES:
        return None, _degraded_meta(
            f"speech audio shorter than one {MIN_STFT_SAMPLES}-sample STFT frame",
            hf_ratio=0.0, low_energy=0.0, high_energy=0.0
        )

    n_mels = 128
    mel_spec = librosa.feature.melspectrogram(
        y=speech_audio,
        sr=sr,
        n_fft=512,
        hop_length=128,
        n_mels=n_mels,
        fmax=8000
    )

    # Bands split at true 4000Hz boundary (mel band 99 for n_mels=128, fmax=8000, sr=16000).
    # Bands 0-98: 0 to ~4000Hz; Bands 99-127: ~4000Hz to 8000Hz (BUG-12 fix).
    MEL_SPLIT_4KHZ = 99
    low_band = mel_spec[:MEL_SPLIT_4KHZ, :]
    high_band = mel_spec[MEL_SPLIT_4KHZ:, :]

    low_energy = float(np.mean(low_band))
    high_energy = float(np.mean(high_band))
    hf_ratio = high_energy / (low_energy + 1e-10)

    # In natural human speech, acoustic vocal dynamics roll off steeply above 4kHz
    # (resulting in a low hf_ratio in [0.001, 0.015]). Pure synthetic TTS or high-frequency
    # vocoder artifacts exhibit elevated HF energy (hf_ratio >= 0.02).
    # Fixed calibration inversion (BUG-10 fix): reward natural acoustic roll-off and
    # penalise excessive synthetic high-frequency energy.
    score = max(0.0, min(1.0, 1.0 - (hf_ratio / 0.04)))

    return round(score, 3), _measured_meta(
        hf_ratio=round(hf_ratio, 4),
        low_energy=round(low_energy, 6),
        high_energy=round(high_energy, 6)
    )


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


def _compute_composite_score(
    noise_score: Optional[float], flux_score: Optional[float], hf_score: Optional[float]
) -> Optional[float]:
    """Weighted composite over the heuristics that measured; None if none did."""
    parts = [
        (noise_score, NOISE_WEIGHT),
        (flux_score, FLUX_WEIGHT),
        (hf_score, HF_RATIO_WEIGHT),
    ]
    measured = [(score, weight) for score, weight in parts if score is not None]
    if not measured:
        return None
    total_weight = sum(weight for _, weight in measured)
    composite = sum(score * weight for score, weight in measured) / total_weight
    return round(min(max(composite, 0.0), 1.0), 3)


def _fmt_score(score: Optional[float]) -> str:
    return "n/a" if score is None else f"{score:.3f}"


def _build_advisory_error_result(
    reason: str,
    error: Optional[str],
    segments_count: int = 0,
    elapsed: float = 0.0
) -> DetectorResult:
    """Advisory result for error cases (passed=True, score=None)."""
    return DetectorResult(
        score=None,
        passed=True,  # Advisory only: never fails the session
        reason=reason,
        error=error,
        details={
            "voice_authenticity_score": None,
            "noise_floor_score": None,
            "spectral_flux_score": None,
            "hf_ratio_score": None,
            "speech_segments_analysed": segments_count,
            "analysis_duration_seconds": elapsed,
            # No measurement happened at all on this path; score is null, not a placeholder.
            "voice_degraded": True,
            "voice_degraded_reasons": [reason]
        }
    )


@dataclass
class _Measurements:
    """What the three heuristics returned: score (None if unmeasurable) and metrics each."""
    noise: Tuple[Optional[float], Dict[str, Any]]
    flux: Tuple[Optional[float], Dict[str, Any]]
    hf: Tuple[Optional[float], Dict[str, Any]]

    def metas(self) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        return self.noise[1], self.flux[1], self.hf[1]


def _build_advisory_success_result(
    score: float, m: _Measurements, segments_count: int, elapsed: float
) -> DetectorResult:
    """Advisory result for a successful analysis (at least one heuristic measured)."""
    noise_score, flux_score, hf_score = m.noise[0], m.flux[0], m.hf[0]
    degraded, degraded_reasons = _collect_degradations(*m.metas())
    reason = (
        f"Voice authenticity score: {score:.3f} "
        f"(noise_floor={_fmt_score(noise_score)}, spectral_flux={_fmt_score(flux_score)}, hf_ratio={_fmt_score(hf_score)})."
    )
    if degraded:
        # Surface partial measurement in the human-readable field too, not just telemetry.
        reason += (
            f" DEGRADED - {len(degraded_reasons)} of 3 heuristics could not measure"
            f" and was excluded from the composite: {'; '.join(degraded_reasons)}."
        )
    return DetectorResult(
        score=score,
        passed=True,  # Advisory only
        reason=reason,
        error=None,
        details={
            "voice_authenticity_score": score,
            "noise_floor_score": noise_score,
            "spectral_flux_score": flux_score,
            "hf_ratio_score": hf_score,
            "speech_segments_analysed": segments_count,
            "heuristic_weights": {"noise": NOISE_WEIGHT, "flux": FLUX_WEIGHT, "hf_ratio": HF_RATIO_WEIGHT},
            "analysis_duration_seconds": elapsed,
            # True when at least one heuristic could not measure and was excluded from the composite.
            "voice_degraded": degraded,
            "voice_degraded_reasons": degraded_reasons,
            "metrics": {"noise": m.noise[1], "flux": m.flux[1], "hf": m.hf[1]},
        }
    )


def _measure(audio: np.ndarray, sr: int, duration: float, segments: List[Dict[str, float]]) -> _Measurements:
    speech_audio = _extract_speech_audio(audio, sr, segments)
    return _Measurements(
        noise=compute_noise_floor_score(audio, sr, segments, duration),
        flux=compute_spectral_flux_score(speech_audio, sr),
        hf=compute_hf_rolloff_score(speech_audio, sr),
    )


def run_voice_authenticity(
    wav_path: Path | str,
    speech_segments: Optional[List[Dict[str, float]]] = None
) -> DetectorResult:
    """
    Run the voice-authenticity check on a 16kHz mono WAV file.

    Never raises. It is advisory: passed=True on a normal run, and also on an unexpected
    failure (then with score=None and the error populated).
    """
    started = time.perf_counter()
    path_obj = Path(wav_path)
    segments = speech_segments or []

    if not path_obj.exists():
        return _build_advisory_error_result(
            reason=f"Audio file not found for voice authenticity analysis: {path_obj}",
            error="Audio file does not exist",
        )

    try:
        audio, sr, duration = read_wav_numpy(path_obj, require_16k=True)
        if len(audio) == 0:
            return _build_advisory_error_result(
                reason="Audio file is empty for voice authenticity analysis.", error="Empty audio file"
            )

        measurements = _measure(audio, sr, duration, segments)
        score = _compute_composite_score(measurements.noise[0], measurements.flux[0], measurements.hf[0])
        elapsed = round(time.perf_counter() - started, 3)
        if score is None:
            _, reasons = _collect_degradations(*measurements.metas())
            return _build_advisory_error_result(
                reason="No voice-authenticity heuristic could measure this audio: " + "; ".join(reasons),
                error="No measurable heuristics",
                segments_count=len(segments),
                elapsed=elapsed,
            )
        return _build_advisory_success_result(score, measurements, len(segments), elapsed)
    except Exception as e:  # noqa: BLE001 - a detector must never raise
        logger.exception("Unexpected error in run_voice_authenticity")
        return _build_advisory_error_result(
            reason=f"Voice authenticity analysis encountered unexpected error: {type(e).__name__}: {e}",
            error=f"{type(e).__name__}: {e}",
            segments_count=len(segments),
            elapsed=round(time.perf_counter() - started, 3),
        )
