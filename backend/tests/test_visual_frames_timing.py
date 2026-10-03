"""
Tests for dense, real-timestamped frame extraction and the lip series built from it
(B4 `time_seconds`, B6 dense sampling, decision D-19).
"""
from __future__ import annotations

import secrets
import threading
from pathlib import Path

import av
import pytest

from app.modules.frame_extraction import extract_frames
from app.modules.visual._frames import MAX_VISUAL_FRAMES, extract_visual_frames
from app.modules.visual._lip_series import build_lip_series
from app.modules.audio._av_alignment import run_av_alignment
from _audio_fixtures import GENUINE_5WORD_WEBM

FIXTURES = Path(__file__).resolve().parent.parent / "prototypes" / "fixtures"
VIDEO_WEBM = FIXTURES / "real_742.webm"  # browser-style VP8 webm; OpenCV reports 1000 fps for it


def _container_truth(path: Path):
    with av.open(str(path)) as c:
        return [float(f.time) for f in c.decode(c.streams.video[0])]


@pytest.mark.skipif(not VIDEO_WEBM.exists(), reason="video fixture missing")
def test_timestamps_are_the_containers_real_presentation_times():
    truth = _container_truth(VIDEO_WEBM)
    res = extract_visual_frames(VIDEO_WEBM)

    assert res.error is None
    assert len(res.frames) == len(res.timestamps) == len(res.original_indices)
    # exact match, frame for frame (the previous OpenCV clock was one frame late)
    for t, i in zip(res.timestamps, res.original_indices):
        assert t == pytest.approx(truth[i], abs=1e-3)


@pytest.mark.skipif(not VIDEO_WEBM.exists(), reason="video fixture missing")
def test_timestamps_strictly_increase_and_fps_is_real_not_1000():
    res = extract_visual_frames(VIDEO_WEBM)

    assert all(b > a for a, b in zip(res.timestamps, res.timestamps[1:])), "duplicate/non-monotonic time"
    assert 5 < res.fps < 120, f"fps {res.fps} is not a real frame rate"


@pytest.mark.skipif(not VIDEO_WEBM.exists(), reason="video fixture missing")
def test_dense_sampling_is_denser_than_the_30_frame_detector_sample_and_capped():
    dense = extract_visual_frames(VIDEO_WEBM)
    sparse = extract_frames(str(VIDEO_WEBM))

    assert len(dense.frames) > len(sparse.frames)
    assert len(dense.frames) <= MAX_VISUAL_FRAMES
    assert dense.frames[0].ndim == 3 and dense.frames[0].shape[2] == 3  # RGB


@pytest.mark.skipif(not GENUINE_5WORD_WEBM.exists(), reason="audio-only fixture missing")
def test_audio_only_media_returns_an_error_instead_of_hanging():
    """Regression: cv2 `cap.read()` blocked forever on an audio-only container."""
    results = {}

    def run():
        results["visual"] = extract_visual_frames(GENUINE_5WORD_WEBM)
        results["shared"] = extract_frames(str(GENUINE_5WORD_WEBM))

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=20)

    assert not t.is_alive(), "frame extraction hung on an audio-only file"
    for key in ("visual", "shared"):
        assert results[key].frames == []
        assert "video" in results[key].error.lower()


def test_missing_and_garbage_files_never_raise(tmp_path):
    assert extract_visual_frames(tmp_path / "nope.webm").error
    junk = tmp_path / "junk.webm"
    junk.write_bytes(b"not a video" * 50)
    assert extract_visual_frames(junk).error


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
    """Without a real timestamp the field is omitted; Stage 4 then degrades instead of mis-scoring."""
    feats = {"frames": [{"mouth_open": 0.03, "time_seconds": None, "original_index": i} for i in range(30)]}
    data = build_lip_series(feats, fps)

    assert all("time_seconds" not in entry for entry in data["series"])
    words = [{"word": "a", "start": 1.0, "end": 1.4, "probability": 0.9}]
    res = run_av_alignment("x.wav", words, data)
    assert res.score is None and res.details["degraded"] is True


def test_real_timestamps_flow_into_stage4_and_score():
    words = [{"word": "a", "start": 1.0, "end": 1.4, "probability": 0.9}]
    times = [i * 0.1 for i in range(100)]
    feats = {"frames": [
        {"mouth_open": 0.25 if 0.7 <= t <= 1.7 else 0.03, "time_seconds": t, "original_index": i}
        for i, t in enumerate(times)
    ]}
    res = run_av_alignment("x.wav", words, build_lip_series(feats, 1000.0))

    assert res.score == 1.0


def test_challenge_selection_uses_the_os_csprng():
    from app.api.v1.endpoints import sessions

    assert isinstance(sessions._rng, secrets.SystemRandom)
