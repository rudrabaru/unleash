"""
Unit and integration tests for Stage 2 Phrase Compliance (faster-whisper).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.modules.audio import process_audio_pipeline
from app.modules.audio._phrase_compliance import (
    _WHISPER_MODEL,
    extract_digits,
    longest_common_subsequence,
    positional_window_match,
    run_phrase_compliance,
)
from app.schemas.detector import DetectorResult

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "prototypes" / "fixtures"
OUT_DIR = Path(__file__).resolve().parent.parent / "prototypes" / "out"


def test_whisper_model_loaded():
    """Verify faster-whisper model is loaded once at module initialization."""
    assert _WHISPER_MODEL is not None, "Whisper model should be loaded at module initialization"


def test_digit_extraction_logic():
    """Test comprehensive digit extraction across diverse speech formats."""
    # Direct numeric
    assert extract_digits("7, 4, 2.") == [7, 4, 2]
    assert extract_digits("742") == [7, 4, 2]
    assert extract_digits("7-4-2") == [7, 4, 2]
    assert extract_digits("7 4 2") == [7, 4, 2]

    # Digit words
    assert extract_digits("seven four two") == [7, 4, 2]
    assert extract_digits("seven, four, two") == [7, 4, 2]

    # Compound & hundreds
    assert extract_digits("seven forty-two") == [7, 4, 2]
    assert extract_digits("seven forty two") == [7, 4, 2]
    assert extract_digits("seven hundred forty-two") == [7, 4, 2]
    assert extract_digits("seven hundred and forty two") == [7, 4, 2]
    assert extract_digits("three hundred eight") == [3, 0, 8]
    assert extract_digits("three hundred and eight") == [3, 0, 8]

    # Hesitations and colloquial
    assert extract_digits("um seven... uh... four... two") == [7, 4, 2]
    assert extract_digits("three oh eight") == [3, 0, 8]
    assert extract_digits("three zero eight") == [3, 0, 8]
    # Note: "for" is no longer mapped to "4" to reduce false-accept risk from common English words
    assert extract_digits("seven for two") == [7, 2]

    # Empty & non-digit speech
    assert extract_digits("") == []
    assert extract_digits("hello how are you") == []


def test_matching_algorithm():
    """Test 2-of-3 threshold and matching calculation."""
    target = [7, 4, 2]

    # 3/3 matches
    assert positional_window_match([7, 4, 2], target) == 3
    assert positional_window_match([0, 7, 4, 2], target) == 3  # with leading noise

    # 2/3 matches (Passing hard gate)
    assert positional_window_match([7, 4, 9], target) == 2
    assert positional_window_match([7, 4], target) == 2
    assert positional_window_match([4, 2], target) == 2
    assert positional_window_match([7, 2], target) == 2

    # 1/3 match (Failing hard gate: < 2)
    assert positional_window_match([7, 1, 9], target) == 1
    assert positional_window_match([7], target) == 1
    assert positional_window_match([1, 2, 3], target) == 1  # 2 is common, but 1 < 2 -> fails hard gate

    # 0/3 match (Failing hard gate: 0)
    assert positional_window_match([1, 5, 8], target) == 0
    assert positional_window_match([], target) == 0


def test_invalid_challenge_phrase():
    """Test invalid challenge phrase format returns appropriate DetectorResult error."""
    fake_wav = OUT_DIR / "real_742_16k.wav"
    res = run_phrase_compliance(fake_wav, "invalid_phrase")
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None
    assert res.error == "Invalid challenge phrase format"


def test_nonexistent_audio_file():
    """Test missing WAV file is handled gracefully."""
    fake_wav = Path("nonexistent_path_audio_123.wav")
    res = run_phrase_compliance(fake_wav, "742")
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None
    assert res.error == "Audio file does not exist"


def test_run_phrase_compliance_real_fixture():
    """Test Stage 2 on real speech WAV fixture ('seven four two')."""
    wav_path = OUT_DIR / "real_742_16k.wav"
    if not wav_path.exists():
        pytest.skip(f"Fixture {wav_path} not found")

    # Positive match: challenge "742"
    res = run_phrase_compliance(wav_path, "742")
    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.error is None
    assert res.score is not None and res.score >= 0.67
    assert res.details is not None
    assert res.details["phrase_matched"] is True
    assert res.details["target_digits"] == [7, 4, 2]
    assert len(res.details["word_timestamps"]) > 0

    # Negative match: wrong challenge "123"
    res_neg = run_phrase_compliance(wav_path, "123")
    assert isinstance(res_neg, DetectorResult)
    assert res_neg.passed is False
    assert res_neg.error is None
    assert res_neg.score is not None and res_neg.score < 0.67
    assert res_neg.details is not None
    assert res_neg.details["phrase_matched"] is False


def test_run_phrase_compliance_tts_fixture():
    """Test Stage 2 on synthetic TTS WAV fixture ('seven four two')."""
    wav_path = OUT_DIR / "tts_742_16k.wav"
    if not wav_path.exists():
        pytest.skip(f"Fixture {wav_path} not found")

    res = run_phrase_compliance(wav_path, "742")
    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.error is None
    assert res.score is not None and res.score >= 0.67
    assert res.details["phrase_matched"] is True


def test_pipeline_integration_real_phrase_pass():
    """Test complete audio pipeline with correct challenge phrase on real WebM file."""
    real_webm = FIXTURES_DIR / "real_742.webm"
    if not real_webm.exists():
        pytest.skip(f"Fixture {real_webm} not found")

    res = asyncio.run(process_audio_pipeline(str(real_webm), "742"))
    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.error is None
    assert res.score is not None and res.score >= 0.67
    assert res.details is not None
    assert res.details["speech_detected"] is True
    assert res.details["phrase_matched"] is True
    assert res.details["word_timestamps"] is not None
    assert len(res.details["word_timestamps"]) > 0


def test_pipeline_integration_wrong_phrase_fail():
    """Test complete audio pipeline with wrong challenge phrase (Scenario 5: hard gate)."""
    real_webm = FIXTURES_DIR / "real_742.webm"
    if not real_webm.exists():
        pytest.skip(f"Fixture {real_webm} not found")

    # Saying "742" but challenge is "981"
    res = asyncio.run(process_audio_pipeline(str(real_webm), "981"))
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.error is None
    assert res.score is None  # Gate rejection yields score=None in pipeline result
    assert res.details is not None
    assert res.details["speech_detected"] is True
    assert res.details["phrase_matched"] is False
