"""
Tests for Stage 4: AV Temporal Alignment (Cross-Modal) [REAL].
Verifies:
1. Real interface adheres strictly to the 4-key contract (DetectorResult)
2. Advisory soft gate behavior: passed=True always (No Hardcoded Stub Values rule:
   score is None only when data is genuinely missing/non-overlapping, never faked)
3. The real alignment computation against synthetic lip-series/word-timestamp data
4. Integration with pipeline orchestrator: word_timestamps flow through and details merge
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.modules.audio import process_audio_pipeline
from app.modules.audio._av_alignment import run_av_alignment
from app.schemas.detector import DetectorResult

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "prototypes" / "fixtures"

WORDS = [
    {"word": "seven", "start": 1.0, "end": 1.5, "probability": 0.99},
    {"word": "four", "start": 1.7, "end": 2.1, "probability": 0.98},
    {"word": "two", "start": 2.3, "end": 2.7, "probability": 0.99},
]


def _lip_series(fps: float, series: list) -> dict:
    return {"fps": fps, "series": series}


def test_stage4_missing_lip_data_degrades_honestly():
    """No lip data at all -> score=None, passed=True, degraded_reason set (never a fake number)."""
    res = run_av_alignment("dummy.wav", word_timestamps=WORDS, lip_openness_data=None)

    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.score is None
    assert res.error is None
    assert res.details["degraded"] is True
    assert res.details["word_count"] == 3


def test_stage4_missing_word_timestamps_degrades_honestly():
    lip_data = _lip_series(30.0, [{"frame_index": 0, "lip_openness_ratio": 0.05}])
    res = run_av_alignment("dummy.wav", word_timestamps=None, lip_openness_data=lip_data)

    assert res.passed is True
    assert res.score is None
    assert res.details["word_count"] == 0


def test_stage4_computes_real_score_when_mouth_moves_with_speech():
    """
    Realistic 15s clip (450 frames @ 30fps): mouth is closed almost the entire time,
    briefly open only during each word's window — mirrors an actual challenge recording
    where 3 short digits are spoken within a much longer silent baseline.
    """
    fps = 30.0
    series = []
    for frame_index in range(0, 450):
        t = frame_index / fps
        is_speaking = any(w["start"] - 0.3 <= t <= w["end"] + 0.3 for w in WORDS)
        series.append({"frame_index": frame_index, "lip_openness_ratio": 0.25 if is_speaking else 0.03})

    res = run_av_alignment("dummy.wav", word_timestamps=WORDS, lip_openness_data=_lip_series(fps, series))

    assert res.passed is True
    assert res.error is None
    assert res.score == 1.0
    assert res.details["words_aligned"] == 3
    assert res.details["words_judged"] == 3


def test_stage4_computes_real_score_when_mouth_never_moves():
    """Mouth stays closed the whole time -> alignment score should be 0.0, not None (data existed)."""
    fps = 30.0
    series = [{"frame_index": i, "lip_openness_ratio": 0.03} for i in range(0, 450)]

    res = run_av_alignment("dummy.wav", word_timestamps=WORDS, lip_openness_data=_lip_series(fps, series))

    assert res.passed is True
    assert res.score == 0.0
    assert res.details["words_aligned"] == 0


def test_stage4_no_frame_overlap_degrades_honestly():
    """Lip series exists but covers a completely different time range than the words."""
    fps = 30.0
    series = [{"frame_index": i, "lip_openness_ratio": 0.2} for i in range(1000, 1010)]

    res = run_av_alignment("dummy.wav", word_timestamps=WORDS, lip_openness_data=_lip_series(fps, series))

    assert res.passed is True
    assert res.score is None
    assert res.details["degraded"] is True


def test_stage4_pipeline_integration_without_lip_data_still_passes():
    """End-to-end: orchestrator's caller contract (lip_openness_data optional) still works."""
    real_fixture = FIXTURES_DIR / "real_742.webm"
    if not real_fixture.exists():
        pytest.skip(f"Fixture {real_fixture} not found")

    res = asyncio.run(process_audio_pipeline(str(real_fixture), "742"))

    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.details is not None
    assert "word_timestamps" in res.details
    assert len(res.details["word_timestamps"]) > 0
    # real_742.webm's video track has no face (see test_visual_module.py), so no lip
    # series is available here -> Stage 4 degrades honestly rather than faking a score.
    assert res.details.get("av_alignment_score") is None
