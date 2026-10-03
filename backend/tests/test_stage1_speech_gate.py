"""
Unit and integration tests for Stage 1 Speech Gate and Audio Extraction.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.modules.audio import process_audio_pipeline
from app.modules.audio._extraction import (
    check_extraction_completeness,
    extract_wav,
    probe_media,
    verify_wav,
)
from app.modules.audio._speech_gate import (
    SPEECH_DURATION_THRESHOLD_S,
    TARGET_SAMPLE_RATE,
    _VAD_MODEL,
    run_speech_gate,
)
from app.schemas.detector import DetectorResult
from _audio_fixtures import GENUINE_5WORD_PHRASE, GENUINE_5WORD_WEBM

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "prototypes" / "fixtures"


def test_vad_model_loaded():
    """Verify silero-vad model is loaded once at module initialization."""
    assert _VAD_MODEL is not None, "VAD model should be loaded at module initialization"


def test_silence_rejected():
    """Verify silence is rejected by speech gate (speech_detected=False, passed=False)."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = Path(f.name)

    try:
        # Create 5.0 seconds of pure silence at 16kHz mono
        data = np.zeros(TARGET_SAMPLE_RATE * 5, dtype=np.float32)
        sf.write(str(temp_path), data, TARGET_SAMPLE_RATE)

        res = run_speech_gate(temp_path)
        assert isinstance(res, DetectorResult)
        assert res.passed is False
        assert res.error is None
        assert res.score is None
        assert res.details is not None
        assert res.details.get("speech_detected") is False
        assert res.details.get("speech_duration_seconds") == 0.0
    finally:
        if temp_path.exists():
            temp_path.unlink()


def test_tone_rejected():
    """Verify non-speech audio (sine tone) is rejected by speech gate."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = Path(f.name)

    try:
        # Create 5.0 seconds of 440Hz sine tone at 16kHz mono
        t = np.linspace(0, 5.0, TARGET_SAMPLE_RATE * 5, endpoint=False)
        data = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        sf.write(str(temp_path), data, TARGET_SAMPLE_RATE)

        res = run_speech_gate(temp_path)
        assert isinstance(res, DetectorResult)
        assert res.passed is False
        assert res.error is None
        assert res.score is None
        assert res.details is not None
        assert res.details.get("speech_detected") is False
    finally:
        if temp_path.exists():
            temp_path.unlink()


def test_empty_wav_handled():
    """Verify an empty WAV file is handled gracefully without crashing."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = Path(f.name)

    try:
        # Create 0 samples WAV
        data = np.array([], dtype=np.float32)
        sf.write(str(temp_path), data, TARGET_SAMPLE_RATE)

        res = run_speech_gate(temp_path)
        assert isinstance(res, DetectorResult)
        assert res.passed is False
        assert res.score is None
    finally:
        if temp_path.exists():
            temp_path.unlink()


def test_corrupt_wav_file_handled():
    """Verify non-WAV garbage bytes do not cause an uncaught exception."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(b"NOT_A_REAL_WAV_HEADER_DATA_1234567890")
        temp_path = Path(f.name)

    try:
        res = run_speech_gate(temp_path)
        assert isinstance(res, DetectorResult)
        assert res.passed is False
        assert res.score is None
        assert res.error is not None
    finally:
        if temp_path.exists():
            temp_path.unlink()


def test_nonexistent_file_handled():
    """Verify missing file does not raise an uncaught exception."""
    fake_path = Path("this_file_definitely_does_not_exist_12345.wav")
    res = run_speech_gate(fake_path)
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None
    assert res.error is not None


def test_extraction_completeness_checker():
    """Verify check_extraction_completeness identifies truncated vs valid extractions."""
    # Complete extraction (100%)
    ok, err = check_extraction_completeness(5.0, 5.0)
    assert ok is True
    assert err is None

    # Normal extraction with minor boundary variance (95%)
    ok, err = check_extraction_completeness(6.0, 5.7)
    assert ok is True
    assert err is None

    # Severe truncation (< 50% threshold, Finding #2)
    ok, err = check_extraction_completeness(5.0, 0.5)
    assert ok is False
    assert "truncated" in err.lower() or "below" in err.lower()

    # Container with missing duration header (common in WebM MediaRecorder)
    ok, err = check_extraction_completeness(None, 4.2)
    assert ok is True
    assert err is None


def test_verify_wav_contract():
    """Verify verify_wav enforces 16000Hz mono contract."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f1, \
         tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f2:
        path_16k_mono = Path(f1.name)
        path_44k_stereo = Path(f2.name)

    try:
        # Valid 16kHz mono
        data1 = np.zeros(16000, dtype=np.float32)
        sf.write(str(path_16k_mono), data1, 16000)
        ok1, desc1 = verify_wav(path_16k_mono)
        assert ok1 is True

        # Invalid 44.1kHz stereo
        data2 = np.zeros((44100, 2), dtype=np.float32)
        sf.write(str(path_44k_stereo), data2, 44100)
        ok2, desc2 = verify_wav(path_44k_stereo)
        assert ok2 is False
        assert "violated" in desc2.lower()
    finally:
        if path_16k_mono.exists():
            path_16k_mono.unlink()
        if path_44k_stereo.exists():
            path_44k_stereo.unlink()


def test_pipeline_with_real_speech_fixture():
    """Test full pipeline end-to-end against a genuine take of the 5-word challenge."""
    import asyncio
    real_webm = GENUINE_5WORD_WEBM
    if not real_webm.exists():
        pytest.skip(f"{real_webm.name} fixture not found")

    res = asyncio.run(process_audio_pipeline(str(real_webm), GENUINE_5WORD_PHRASE))
    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.error is None
    assert res.score is not None and res.score >= 0.6
    assert res.details is not None
    assert res.details["speech_detected"] is True
    assert res.details["speech_duration_seconds"] >= SPEECH_DURATION_THRESHOLD_S


def test_pipeline_with_silence_fixture():
    """Test full pipeline with silence fixture (Scenario 4)."""
    import asyncio
    silence_webm = FIXTURES_DIR / "silence.webm"
    if not silence_webm.exists():
        pytest.skip("silence.webm fixture not found")

    challenge_phrase = "seven four two apple bridge"
    res = asyncio.run(process_audio_pipeline(str(silence_webm), challenge_phrase))
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None
    assert res.error is None
    assert res.details["speech_detected"] is False


def test_pipeline_with_tone_fixture():
    """Test full pipeline with non-speech tone fixture (Scenario 9)."""
    import asyncio
    tone_webm = FIXTURES_DIR / "tone.webm"
    if not tone_webm.exists():
        pytest.skip("tone.webm fixture not found")

    challenge_phrase = "seven four two apple bridge"
    res = asyncio.run(process_audio_pipeline(str(tone_webm), challenge_phrase))
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None
    assert res.error is None
    assert res.details["speech_detected"] is False


def test_pipeline_with_corrupt_fixture():
    """Test full pipeline with corrupt/truncated fixture (Finding #2)."""
    import asyncio
    corrupt_webm = FIXTURES_DIR / "corrupt.webm"
    if not corrupt_webm.exists():
        pytest.skip("corrupt.webm fixture not found")

    challenge_phrase = "seven four two apple bridge"
    res = asyncio.run(process_audio_pipeline(str(corrupt_webm), challenge_phrase))
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None


def test_pipeline_with_garbage_fixture():
    """Test full pipeline with garbage bytes (negative path)."""
    import asyncio
    garbage_webm = FIXTURES_DIR / "garbage.webm"
    if not garbage_webm.exists():
        pytest.skip("garbage.webm fixture not found")

    challenge_phrase = "seven four two apple bridge"
    res = asyncio.run(process_audio_pipeline(str(garbage_webm), challenge_phrase))
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None
    assert res.error is not None


