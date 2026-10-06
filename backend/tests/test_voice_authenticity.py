"""
Tests for the voice-authenticity check (librosa spectral heuristics; advisory only).
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import soundfile as sf

from app.modules.audio import process_audio_pipeline
from app.modules.audio._voice_authenticity import (
    compute_hf_rolloff_score,
    compute_noise_floor_score,
    compute_spectral_flux_score,
    run_voice_authenticity,
)
from app.schemas.detector import DetectorResult
from _paths import OTHER_5WORD_PHRASE


def test_heuristic_functions_smoke():
    """Verify individual spectral heuristic functions execute without errors on synthetic arrays."""
    sr = 16000
    duration = 2.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False, dtype=np.float32)

    # 1. Harmonic synthetic speech-like signal (sum of sinusoids)
    synthetic_speech = (
        0.5 * np.sin(2 * np.pi * 220 * t) +
        0.3 * np.sin(2 * np.pi * 440 * t) +
        0.1 * np.sin(2 * np.pi * 880 * t) +
        0.05 * np.random.normal(0, 0.01, len(t))
    ).astype(np.float32)

    # 2. Noise floor test
    segments = [{"start": 0.5, "end": 1.5}]
    noise_score, noise_meta = compute_noise_floor_score(synthetic_speech, sr, segments, duration)
    assert isinstance(noise_score, float)
    assert 0.0 <= noise_score <= 1.0
    assert "mean_rms" in noise_meta
    assert "cov" in noise_meta

    # 3. Spectral flux test
    flux_score, flux_meta = compute_spectral_flux_score(synthetic_speech, sr)
    assert isinstance(flux_score, float)
    assert 0.0 <= flux_score <= 1.0
    assert "std_flux" in flux_meta

    # 4. HF rolloff test
    hf_score, hf_meta = compute_hf_rolloff_score(synthetic_speech, sr)
    assert isinstance(hf_score, float)
    assert 0.0 <= hf_score <= 1.0
    assert "hf_ratio" in hf_meta


def test_run_voice_authenticity_empty_segments(tmp_path: Path):
    """Verify graceful execution when speech segments list is empty or None."""
    sr = 16000
    synthetic = np.random.normal(0, 0.1, sr * 2).astype(np.float32)
    wav_path = tmp_path / "test_synth.wav"
    sf.write(str(wav_path), synthetic, sr)

    res = run_voice_authenticity(wav_path, speech_segments=[])
    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.score is not None
    assert 0.0 <= res.score <= 1.0
    assert res.error is None
    assert res.details is not None
    assert res.details["speech_segments_analysed"] == 0


def test_run_voice_authenticity_invalid_path():
    """Verify missing audio file returns passed=True (advisory) with error description."""
    nonexistent = Path("nonexistent_path_to_audio_12345.wav")
    res = run_voice_authenticity(nonexistent)

    assert isinstance(res, DetectorResult)
    assert res.passed is True  # Advisory: the voice check never fails the pipeline
    assert res.score is None
    assert res.error is not None
    assert "Audio file does not exist" in res.error


def test_run_voice_authenticity_empty_file(tmp_path: Path):
    """Verify empty (0 samples) WAV file handling."""
    wav_path = tmp_path / "empty.wav"
    sf.write(str(wav_path), np.array([], dtype=np.float32), 16000)

    res = run_voice_authenticity(wav_path)
    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.score is None
    assert res.error == "Empty audio file"


def test_4key_contract_compliance(tmp_path: Path):
    """Assert all 4-key contract schema properties are strictly adhered to."""
    sr = 16000
    audio = (0.2 * np.sin(2 * np.pi * 300 * np.linspace(0, 3, sr * 3))).astype(np.float32)
    wav_path = tmp_path / "contract_test.wav"
    sf.write(str(wav_path), audio, sr)

    res = run_voice_authenticity(wav_path, [{"start": 0.5, "end": 2.5}])

    # 1. score: float or None
    assert res.score is not None
    assert isinstance(res.score, float)
    assert 0.0 <= res.score <= 1.0

    # 2. passed: boolean
    assert isinstance(res.passed, bool)
    assert res.passed is True

    # 3. reason: non-empty string
    assert isinstance(res.reason, str)
    assert len(res.reason.strip()) > 0

    # 4. error: None on success
    assert res.error is None

    # 5. details: contains all required breakdown fields
    assert res.details is not None
    assert "voice_authenticity_score" in res.details
    assert "noise_floor_score" in res.details
    assert "spectral_flux_score" in res.details
    assert "hf_ratio_score" in res.details
    assert "analysis_duration_seconds" in res.details
    assert "heuristic_weights" in res.details


def test_voice_check_latency_budget(tmp_path: Path):
    """The voice-authenticity check completes within its latency budget (< 1.0 s) on CPU."""
    sr = 16000
    # 6 seconds of speech-like audio
    t = np.linspace(0, 6.0, sr * 6, endpoint=False, dtype=np.float32)
    audio = (0.3 * np.sin(2 * np.pi * 250 * t) + 0.02 * np.random.normal(0, 1, len(t))).astype(np.float32)
    wav_path = tmp_path / "latency_test.wav"
    sf.write(str(wav_path), audio, sr)

    t0 = time.perf_counter()
    res = run_voice_authenticity(wav_path, [{"start": 1.0, "end": 2.0}, {"start": 2.5, "end": 4.5}])
    duration = time.perf_counter() - t0

    assert res.score is not None
    assert duration < 1.0, f"voice check latency {duration:.3f}s exceeded budget of 1.0s"


def test_pipeline_includes_the_voice_check(genuine_pipeline_result):
    """The full pipeline on a genuine recording carries the voice-authenticity result."""
    res = genuine_pipeline_result

    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.score is not None
    assert 0.0 <= res.score <= 1.0
    assert res.error is None

    # The voice-check details are merged into the pipeline details
    details = res.details
    assert details is not None
    assert "voice_authenticity_score" in details
    assert "noise_floor_score" in details
    assert "spectral_flux_score" in details
    assert "hf_ratio_score" in details
    assert "speech_segments_analysed" in details
    assert isinstance(details["voice_authenticity_score"], float)

    # The reason mentions the voice check
    assert "Voice authenticity:" in res.reason


def test_degraded_flag_set_when_heuristic_cannot_measure(tmp_path: Path):
    """
    A fallback branch that returns a placeholder instead of a real measurement must say so
    via details["degraded"], while still honouring the advisory contract (passed=True,
    error=None, numeric score).
    """
    sr = 16000
    # Wall-to-wall speech segment leaves no inter-speech silence for the noise-floor heuristic.
    audio = np.random.normal(0, 0.1, sr * 2).astype(np.float32)
    wav_path = tmp_path / "no_silence.wav"
    sf.write(str(wav_path), audio, sr)

    res = run_voice_authenticity(wav_path, [{"start": 0.0, "end": 2.0}])

    assert res.passed is True
    assert res.error is None
    assert res.score is not None
    assert res.details is not None
    assert res.details["voice_degraded"] is True
    assert any("noise floor" in r for r in res.details["voice_degraded_reasons"])
    assert res.details["metrics"]["noise"]["degraded"] is True
    # The heuristics that did measure must not be flagged.
    assert res.details["metrics"]["flux"]["degraded"] is False
    assert "DEGRADED" in res.reason


def test_degraded_flag_absent_on_fully_measured_run(tmp_path: Path):
    """A run where all three heuristics measure successfully must report degraded=False."""
    sr = 16000
    t = np.linspace(0, 4.0, sr * 4, endpoint=False, dtype=np.float32)
    audio = (0.3 * np.sin(2 * np.pi * 250 * t) + 0.02 * np.random.normal(0, 1, len(t))).astype(np.float32)
    wav_path = tmp_path / "measured.wav"
    sf.write(str(wav_path), audio, sr)

    # Leaves real silence gaps before, between and after the two speech segments.
    res = run_voice_authenticity(wav_path, [{"start": 0.5, "end": 1.5}, {"start": 2.0, "end": 3.0}])

    assert res.details is not None
    assert res.details["voice_degraded"] is False
    assert res.details["voice_degraded_reasons"] == []
    assert "DEGRADED" not in res.reason


def test_pipeline_skips_the_voice_check_when_the_speech_check_fails(silence_webm):
    """If the speech check fails (silence), the voice-authenticity check is not evaluated."""
    res = process_audio_pipeline(str(silence_webm), OTHER_5WORD_PHRASE)

    assert res.passed is False
    assert "voice_authenticity_score" not in (res.details or {})
