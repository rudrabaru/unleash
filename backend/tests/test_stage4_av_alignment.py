"""
Unit and integration tests for Stage 4: AV Temporal Alignment (Cross-Modal) [STUB].
Verifies:
1. Stage 4 stub interface adheres strictly to 4-key contract (DetectorResult)
2. Advisory soft gate behavior: passed=True, score=None (No Hardcoded Stub Values rule)
3. Integration with pipeline orchestrator: word_timestamps are passed and details merged
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.modules.audio import process_audio_pipeline
from app.modules.audio._av_alignment import run_av_alignment
from app.schemas.detector import DetectorResult

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "prototypes" / "fixtures"


def test_stage4_stub_interface_contract():
    """Verify Stage 4 stub returns a valid DetectorResult with score=None and passed=True."""
    dummy_timestamps = [
        {"word": "seven", "start": 1.0, "end": 1.5, "probability": 0.99},
        {"word": "four", "start": 1.7, "end": 2.1, "probability": 0.98},
        {"word": "two", "start": 2.3, "end": 2.7, "probability": 0.99},
    ]

    res = run_av_alignment(
        wav_path="dummy.wav",
        word_timestamps=dummy_timestamps,
        lip_openness_data=None,
    )

    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.score is None
    assert res.error is None
    assert "[STUB]" in res.reason
    assert res.details is not None
    assert res.details.get("stub") is True
    assert res.details.get("av_alignment_score") is None
    assert res.details.get("word_count") == 3


def test_stage4_stub_handles_empty_inputs():
    """Verify Stage 4 stub handles None/empty inputs without raising exceptions."""
    res = run_av_alignment("dummy.wav", word_timestamps=None, lip_openness_data=None)

    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.score is None
    assert res.error is None
    assert res.details.get("word_count") == 0


def test_stage4_pipeline_integration():
    """Verify Stage 4 stub is executed and merged in end-to-end audio pipeline."""
    real_fixture = FIXTURES_DIR / "real_742.webm"
    if not real_fixture.exists():
        pytest.skip(f"Fixture {real_fixture} not found")

    res = asyncio.run(process_audio_pipeline(str(real_fixture), "742"))

    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.details is not None
    assert res.details.get("stub") is True
    assert res.details.get("av_alignment_score") is None
    assert "word_timestamps" in res.details
    assert len(res.details["word_timestamps"]) > 0
