"""
Tests for the lip-sync check (audio-visual temporal alignment).
Verifies:
1. Real interface adheres strictly to the 4-key contract (DetectorResult)
2. Advisory behaviour: passed=True always (score is None only when data is genuinely
   missing or non-overlapping, never faked)
3. The real alignment computation against synthetic lip-series/word-timestamp data
4. Integration with the audio pipeline: word_timestamps flow through and details merge
"""
from __future__ import annotations

import pytest

from app.modules.audio._av_alignment import run_av_alignment
from app.schemas.detector import DetectorResult

WORDS = [
    {"word": "walnut", "start": 1.0, "end": 1.5, "probability": 0.99},
    {"word": "lantern", "start": 1.7, "end": 2.1, "probability": 0.98},
    {"word": "bicycle", "start": 2.3, "end": 2.7, "probability": 0.99},
]


def _lip_series(fps: float, series: list) -> dict:
    return {"fps": fps, "series": series}


def _entry(index: int, t: float, ratio: float) -> dict:
    return {"frame_index": index, "time_seconds": round(t, 4), "lip_openness_ratio": ratio}


def _speaking(t: float, words=WORDS) -> bool:
    return any(w["start"] - 0.3 <= t <= w["end"] + 0.3 for w in words)


def _timed_series(times, words=WORDS, open_ratio=0.25, closed_ratio=0.03) -> list:
    """Mouth open only while a word (plus tolerance) is being spoken."""
    return [_entry(i, t, open_ratio if _speaking(t, words) else closed_ratio) for i, t in enumerate(times)]


def test_lip_sync_missing_lip_data_degrades_honestly():
    """No lip data at all -> score=None, passed=True, degraded_reason set (never a fake number)."""
    res = run_av_alignment("dummy.wav", word_timestamps=WORDS, lip_openness_data=None)

    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.score is None
    assert res.error is None
    assert res.details["degraded"] is True
    assert res.details["word_count"] == 3


def test_lip_sync_missing_word_timestamps_degrades_honestly():
    lip_data = _lip_series(30.0, [_entry(0, 0.0, 0.05)])
    res = run_av_alignment("dummy.wav", word_timestamps=None, lip_openness_data=lip_data)

    assert res.passed is True
    assert res.score is None
    assert res.details["word_count"] == 0


def test_lip_sync_computes_real_score_when_mouth_moves_with_speech():
    """
    Realistic 15s clip (450 frames @ 30fps): mouth is closed almost the entire time,
    briefly open only during each word's window (a mostly-closed mouth is what makes the per-session threshold work).
    """
    times = [i / 30.0 for i in range(450)]
    res = run_av_alignment("dummy.wav", word_timestamps=WORDS, lip_openness_data=_lip_series(30.0, _timed_series(times)))

    assert res.passed is True
    assert res.error is None
    assert res.score == 1.0
    assert res.details["words_aligned"] == 3
    assert res.details["words_judged"] == 3
    assert res.details["lip_samples_used"] == 450


def test_lip_sync_browser_style_clock_is_not_confused_by_bogus_fps():
    """
    The failure mode this guards against: OpenCV reports 1000 fps for browser .webm and frame_index counts
    subsampled frames. Timing now comes from time_seconds, so the fps value is irrelevant.
    A dense, evenly spaced 15 s sample (~10 fps) must score from real timestamps.
    """
    times = [i * 0.1 for i in range(150)]
    res = run_av_alignment("dummy.wav", word_timestamps=WORDS, lip_openness_data=_lip_series(1000.0, _timed_series(times)))

    assert res.score == 1.0
    assert res.details["degraded"] is False


def test_lip_sync_sparse_30_frame_sample_still_scores_from_real_times():
    """30 frames over 15 s (one per 0.5 s) -> each word window still catches >= 1 sample."""
    times = [i * 0.5 for i in range(30)]
    res = run_av_alignment("dummy.wav", word_timestamps=WORDS, lip_openness_data=_lip_series(2.0, _timed_series(times)))

    assert res.score is not None
    assert res.details["words_judged"] >= 1


def test_lip_sync_irregular_timestamps_variable_frame_rate():
    """Variable-frame-rate recordings: spacing is uneven, matching is by time not index."""
    times, t = [], 0.0
    while t < 15.0:
        times.append(t)
        t += 0.05 if int(t) % 2 == 0 else 0.2
    res = run_av_alignment("dummy.wav", word_timestamps=WORDS, lip_openness_data=_lip_series(30.0, _timed_series(times)))

    assert res.score == 1.0


def test_lip_sync_speech_with_mouth_moving_at_the_wrong_time_scores_low():
    """Replay/TTS-style mismatch: lips move 8 s after the words were spoken."""
    shifted = [{**w, "start": w["start"] + 8.0, "end": w["end"] + 8.0} for w in WORDS]
    times = [i / 30.0 for i in range(450)]
    res = run_av_alignment("dummy.wav", word_timestamps=WORDS, lip_openness_data=_lip_series(30.0, _timed_series(times, words=shifted)))

    assert res.score == 0.0
    assert res.details["words_aligned"] == 0


def test_lip_sync_computes_real_score_when_mouth_never_moves():
    """Mouth stays closed the whole time -> alignment score should be 0.0, not None (data existed)."""
    series = [_entry(i, i / 30.0, 0.03) for i in range(450)]

    res = run_av_alignment("dummy.wav", word_timestamps=WORDS, lip_openness_data=_lip_series(30.0, series))

    assert res.passed is True
    assert res.score == 0.0
    assert res.details["words_aligned"] == 0


def test_lip_sync_series_without_time_seconds_degrades_instead_of_guessing():
    """Old shape (frame_index only) must NOT be converted with fps: that gave wrong scores."""
    series = [{"frame_index": i, "lip_openness_ratio": 0.25 if i < 30 else 0.03} for i in range(450)]

    res = run_av_alignment("dummy.wav", word_timestamps=WORDS, lip_openness_data=_lip_series(30.0, series))

    assert res.passed is True
    assert res.score is None
    assert res.details["degraded"] is True
    assert "time_seconds" in res.details["degraded_reason"]


@pytest.mark.parametrize("bad_time", [float("nan"), float("inf"), -1.0, None, "1.5", True])
def test_lip_sync_invalid_timestamps_are_ignored(bad_time):
    series = [{"frame_index": i, "time_seconds": bad_time, "lip_openness_ratio": 0.2} for i in range(50)]

    res = run_av_alignment("dummy.wav", word_timestamps=WORDS, lip_openness_data=_lip_series(30.0, series))

    assert res.score is None
    assert res.details["degraded"] is True
    assert res.error is None


def test_lip_sync_mixed_valid_and_invalid_samples_use_only_the_valid_ones():
    times = [i / 30.0 for i in range(450)]
    series = _timed_series(times) + [{"frame_index": 999, "time_seconds": float("nan"), "lip_openness_ratio": 0.9}]

    res = run_av_alignment("dummy.wav", word_timestamps=WORDS, lip_openness_data=_lip_series(30.0, series))

    assert res.score == 1.0
    assert res.details["lip_samples_used"] == 450


def test_lip_sync_no_frame_overlap_degrades_honestly():
    """Lip series exists but covers a completely different time range than the words."""
    series = [_entry(i, 40.0 + i / 30.0, 0.2) for i in range(10)]

    res = run_av_alignment("dummy.wav", word_timestamps=WORDS, lip_openness_data=_lip_series(30.0, series))

    assert res.passed is True
    assert res.score is None
    assert res.details["degraded"] is True


def test_lip_sync_malformed_word_never_raises():
    """A word dict missing start/end must produce a contract-valid result, not an exception."""
    res = run_av_alignment("dummy.wav", word_timestamps=[{"word": "x"}], lip_openness_data=_lip_series(30.0, [_entry(0, 1.0, 0.2)]))

    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.score is None


def test_lip_sync_pipeline_integration_without_lip_data_still_passes(genuine_pipeline_result):
    """End-to-end: the caller contract (lip_openness_data optional) still works."""
    res = genuine_pipeline_result

    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.details is not None
    assert "word_timestamps" in res.details
    assert len(res.details["word_timestamps"]) > 0
    # genuine_5word.webm has no video track, so no lip series is available here
    # -> the lip-sync check degrades honestly rather than faking a score.
    assert res.details.get("av_alignment_score") is None

