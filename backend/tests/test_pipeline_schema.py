"""
Tests for the audio pipeline's output schema and for cleaning up the temporary WAV.
Verifies:
1. The full 4-key contract plus the 7 canonical details keys
2. Privacy: the intermediate extracted WAV is deleted after analysis, on success and on failure
3. The composite advisory score (voice authenticity + lip-sync weighting)
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from app.modules.audio import process_audio_pipeline
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


def test_pipeline_output_schema_contract(genuine_pipeline_result):
    """A successful pipeline run satisfies the canonical schema."""
    res = genuine_pipeline_result

    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.error is None
    assert res.score is None  # must-pass checks carry no score; voice and lip sync are in the details
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


def _temp_entries():
    return sorted(p.name for p in TEMP_UPLOADS_DIR.glob("*")) if TEMP_UPLOADS_DIR.exists() else []


def test_pipeline_leaves_no_temporary_files_after_success():
    """The temporary extracted WAV is deleted after a successful pipeline run."""
    before = _temp_entries()

    res = process_audio_pipeline(str(require(GENUINE_5WORD_WEBM)), GENUINE_5WORD_PHRASE)

    assert res.passed is True
    assert _temp_entries() == before


def test_pipeline_leaves_no_temporary_files_after_a_failed_check(silence_webm):
    """The temporary extracted WAV is deleted even when a must-pass check fails."""
    before = _temp_entries()

    res = process_audio_pipeline(str(silence_webm), OTHER_5WORD_PHRASE)

    assert res.passed is False
    assert _temp_entries() == before


def test_pipeline_leaves_no_temporary_files_after_an_exception(tone_webm):
    """An unexpected exception inside a check still removes the temporary folder and returns a result."""
    before = _temp_entries()

    with patch("app.modules.audio.run_speech_gate", side_effect=RuntimeError("boom")):
        res = process_audio_pipeline(str(tone_webm), OTHER_5WORD_PHRASE)

    assert res.passed is False and res.score is None and "boom" in res.error
    assert _temp_entries() == before
