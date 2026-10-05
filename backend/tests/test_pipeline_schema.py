"""
Tests for the audio pipeline's output schema and for cleaning up the temporary WAV.
Verifies:
1. The full 4-key contract plus the 7 canonical details keys
2. Privacy: the intermediate extracted WAV is deleted after analysis, on success and on failure
3. The composite advisory score (voice authenticity + lip-sync weighting)
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import settings
from app.modules.audio import _compute_pipeline_score, process_audio_pipeline
from app.schemas.detector import DetectorResult
from _paths import GENUINE_5WORD_PHRASE, GENUINE_5WORD_WEBM, OTHER_5WORD_PHRASE, require

TEMP_UPLOADS_DIR = Path(settings.UPLOAD_TEMP_DIR)

# Canonical details keys and their expected types
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
    """A successful pipeline run satisfies the canonical schema."""
    res = asyncio.run(process_audio_pipeline(str(require(GENUINE_5WORD_WEBM)), GENUINE_5WORD_PHRASE))

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
    """The temporary extracted WAV is deleted after a successful pipeline run."""
    real_fixture = require(GENUINE_5WORD_WEBM)

    expected_wav = TEMP_UPLOADS_DIR / f"{real_fixture.stem}_16k.wav"
    if expected_wav.exists():
        expected_wav.unlink()

    res = asyncio.run(process_audio_pipeline(str(real_fixture), GENUINE_5WORD_PHRASE))
    assert res.passed is True
    assert not expected_wav.exists(), f"Temporary WAV {expected_wav} was not deleted after execution"


def test_pipeline_temp_wav_cleanup_on_failure(silence_webm):
    """The temporary extracted WAV is deleted even when a must-pass check fails."""
    expected_wav = TEMP_UPLOADS_DIR / f"{silence_webm.stem}_16k.wav"
    if expected_wav.exists():
        expected_wav.unlink()

    res = asyncio.run(process_audio_pipeline(str(silence_webm), OTHER_5WORD_PHRASE))
    assert res.passed is False
    assert not expected_wav.exists(), f"Temporary WAV {expected_wav} was not deleted after a failed check"


def test_compute_pipeline_score_voice_check_only():
    """Composite advisory score when the lip-sync check produced no score."""
    s3_res = DetectorResult(score=0.85, passed=True, reason="Authentic", error=None, details={})
    score, score_str = _compute_pipeline_score(s3_res, stage4_score=None)

    assert score == 0.85
    assert score_str == "0.850"


def test_compute_pipeline_score_voice_and_lip_sync():
    """Composite advisory score when both the voice check and the lip-sync check scored."""
    s3_res = DetectorResult(score=0.80, passed=True, reason="Authentic", error=None, details={})
    stage4_score = 0.90

    score, score_str = _compute_pipeline_score(s3_res, stage4_score=stage4_score)

    # 50/50 weighting: (0.80 * 0.5 + 0.90 * 0.5) / 1.0 = 0.85
    assert score == 0.85
    assert score_str == "0.800"


def test_compute_pipeline_score_none_when_no_scores():
    """The composite advisory score is None when no check produced a score."""
    s3_res = DetectorResult(score=None, passed=True, reason="Error", error="err", details={})
    score, score_str = _compute_pipeline_score(s3_res, stage4_score=None)

    assert score is None
    assert score_str == "N/A"
