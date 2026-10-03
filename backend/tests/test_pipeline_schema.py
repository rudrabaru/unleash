"""
Tests for Audio Pipeline Canonical Output Schema Contract and Privacy NFR (Temp WAV cleanup).
Verifies:
1. Full 4-key contract + 7 canonical details keys per Project Plan v2.1 §5.6
2. Privacy NFR §10: intermediate extracted WAV files are cleaned up post-analysis
3. Pipeline composite score calculation logic (Stage 3 + Stage 4 weighting)
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict

import pytest

from app.modules.audio import (
    _STAGE3_ADVISORY_WEIGHT,
    _STAGE4_ADVISORY_WEIGHT,
    _compute_pipeline_score,
    process_audio_pipeline,
)
from app.schemas.detector import DetectorResult
from _audio_fixtures import GENUINE_5WORD_PHRASE, GENUINE_5WORD_WEBM

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "prototypes" / "fixtures"
TEMP_UPLOADS_DIR = Path(__file__).resolve().parent.parent / "temp_uploads"

# Standard 5-word test phrase for consistency across tests
TEST_CHALLENGE_PHRASE = "apple bridge cloud dark eagle"

# Canonical details keys and expected type constraints per Project Plan §5.6
CANONICAL_DETAILS_SCHEMA = {
    "speech_detected": bool,
    "speech_duration_seconds": (float, int),
    "phrase_matched": bool,
    "words_detected": list,
    "transcript": str,
    "voice_authenticity_score": (float, type(None)),
    "av_alignment_score": (float, type(None)),
}


def test_pipeline_output_schema_contract():
    """Verify that a successful pipeline run satisfies the canonical schema with 5-word phrases."""
    real_fixture = GENUINE_5WORD_WEBM
    if not real_fixture.exists():
        pytest.skip(f"Fixture {real_fixture} not found")

    res = asyncio.run(process_audio_pipeline(str(real_fixture), GENUINE_5WORD_PHRASE))

    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.error is None
    assert res.score is not None
    assert isinstance(res.score, float)
    assert 0.0 <= res.score <= 1.0
    assert isinstance(res.reason, str) and len(res.reason) > 0

    assert res.details is not None
    for key, expected_type in CANONICAL_DETAILS_SCHEMA.items():
        assert key in res.details, f"Required canonical key '{key}' missing from details"
        val = res.details[key]
        assert isinstance(val, expected_type), (
            f"Key '{key}' value {val!r} has type {type(val)}, expected {expected_type}"
        )

    # Specific contract assertions
    assert res.details["speech_detected"] is True
    assert res.details["speech_duration_seconds"] >= 2.0
    assert res.details["phrase_matched"] is True
    assert isinstance(res.details["words_detected"], list)


def test_pipeline_temp_wav_cleanup_on_success():
    """Verify Privacy NFR §10: temporary extracted WAV is deleted after successful pipeline execution."""
    real_fixture = GENUINE_5WORD_WEBM
    if not real_fixture.exists():
        pytest.skip(f"Fixture {real_fixture} not found")

    expected_wav = TEMP_UPLOADS_DIR / f"{real_fixture.stem}_16k.wav"
    if expected_wav.exists():
        expected_wav.unlink()

    res = asyncio.run(process_audio_pipeline(str(real_fixture), GENUINE_5WORD_PHRASE))
    assert res.passed is True
    assert not expected_wav.exists(), f"Temporary WAV {expected_wav} was not deleted after execution"


def test_pipeline_temp_wav_cleanup_on_failure():
    """Verify Privacy NFR §10: temporary extracted WAV is deleted even when a hard gate fails."""
    silence_fixture = FIXTURES_DIR / "silence.webm"
    if not silence_fixture.exists():
        pytest.skip(f"Fixture {silence_fixture} not found")

    expected_wav = TEMP_UPLOADS_DIR / "silence_16k.wav"
    if expected_wav.exists():
        expected_wav.unlink()

    res = asyncio.run(process_audio_pipeline(str(silence_fixture), TEST_CHALLENGE_PHRASE))
    assert res.passed is False
    assert not expected_wav.exists(), f"Temporary WAV {expected_wav} was not deleted after failed gate"


def test_compute_pipeline_score_stage3_only():
    """Verify composite advisory score calculation when Stage 4 is not yet active (stage4_score=None)."""
    s3_res = DetectorResult(score=0.85, passed=True, reason="Authentic", error=None, details={})
    score, score_str = _compute_pipeline_score(s3_res, stage4_score=None)

    assert score == 0.85
    assert score_str == "0.850"


def test_compute_pipeline_score_stage3_and_stage4():
    """Verify composite advisory score calculation when both Stage 3 and Stage 4 are active."""
    s3_res = DetectorResult(score=0.80, passed=True, reason="Authentic", error=None, details={})
    stage4_score = 0.90

    score, score_str = _compute_pipeline_score(s3_res, stage4_score=stage4_score)

    # 50/50 weighting: (0.80 * 0.5 + 0.90 * 0.5) / 1.0 = 0.85
    assert score == 0.85
    assert score_str == "0.800"


def test_compute_pipeline_score_none_when_no_scores():
    """Verify composite advisory score returns None when no stage produced a score."""
    s3_res = DetectorResult(score=None, passed=True, reason="Error", error="err", details={})
    score, score_str = _compute_pipeline_score(s3_res, stage4_score=None)

    assert score is None
    assert score_str == "N/A"
