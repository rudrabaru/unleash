"""
Tests for the lip-openness series handed to the lip-sync check: every sample carries a real
presentation time, and a time is never derived from the (unreliable) frame rate.
"""
import pytest

from app.modules.audio._av_alignment import run_av_alignment
from app.modules.visual._lip_series import build_lip_series


def test_lip_series_carries_real_time_and_original_index():
    feats = {"frames": [
        {"mouth_open": 0.2, "time_seconds": 1.5, "original_index": 45},
        {"mouth_open": None, "time_seconds": 1.6, "original_index": 48},  # no face: omitted
        {"mouth_open": 0.05, "time_seconds": 2.0, "original_index": 60},
    ]}
    series = build_lip_series(feats, 30.0)["series"]

    assert series == [
        {"frame_index": 45, "lip_openness_ratio": 0.2, "time_seconds": 1.5},
        {"frame_index": 60, "lip_openness_ratio": 0.05, "time_seconds": 2.0},
    ]


@pytest.mark.parametrize("fps", [1000.0, 30.0])
def test_lip_series_never_invents_a_time_from_fps(fps):
    """Without a real timestamp the field is omitted; the lip-sync check then degrades instead of mis-scoring."""
    feats = {"frames": [{"mouth_open": 0.03, "time_seconds": None, "original_index": i} for i in range(30)]}
    data = build_lip_series(feats, fps)

    assert all("time_seconds" not in entry for entry in data["series"])
    words = [{"word": "a", "start": 1.0, "end": 1.4, "probability": 0.9}]
    res = run_av_alignment(words, data)
    assert res.score is None and res.details["lip_sync_degraded"] is True


def test_real_timestamps_flow_into_stage4_and_score():
    words = [{"word": "a", "start": 1.0, "end": 1.4, "probability": 0.9}]
    times = [i * 0.1 for i in range(100)]
    feats = {"frames": [
        {"mouth_open": 0.25 if 0.7 <= t <= 1.7 else 0.03, "time_seconds": t, "original_index": i}
        for i, t in enumerate(times)
    ]}
    res = run_av_alignment(words, build_lip_series(feats, 1000.0))

    assert res.score == 1.0
