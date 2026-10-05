"""
Tests for the single-decode frame loader (app.media.frames).

The loader must hand the detectors exactly the frames and real timestamps they used to get from
the two older extractors (this file compares against them while they exist), keep the sparse set
a subset of the dense set, and fail cleanly on files that are not usable video.
"""
import threading

import av
import numpy as np
import pytest

from app.media.frames import MAX_DENSE_FRAMES, MAX_SPARSE_FRAMES, load_frames
from app.media.sampling import sample_indices
from app.modules.frame_extraction import extract_frames
from app.modules.visual._frames import extract_visual_frames
from _paths import GENUINE_5WORD_NOFACE_VIDEO_WEBM, GENUINE_5WORD_WEBM, VIDEO_FIXTURES_DIR, require

CLIPS = [
    pytest.param(GENUINE_5WORD_NOFACE_VIDEO_WEBM, id="browser-vp8"),
    pytest.param(VIDEO_FIXTURES_DIR / "TURN_LEFT.webm", id="turn-left"),
    pytest.param(VIDEO_FIXTURES_DIR / "TURN_RIGHT.webm", id="turn-right"),
    pytest.param(VIDEO_FIXTURES_DIR / "BLINKING.webm", id="blinking-1080p"),
]


def _container_times(path):
    with av.open(str(path)) as container:
        return [float(f.time) for f in container.decode(container.streams.video[0])]


def test_sample_indices():
    assert sample_indices(0, 30) == []
    assert sample_indices(10, 30) == list(range(10))
    assert sample_indices(30, 30) == list(range(30))
    picked = sample_indices(450, 30)
    assert len(picked) == 30 and picked[0] == 0 and picked == sorted(set(picked))
    assert picked[1] == 15


@pytest.mark.parametrize("clip", CLIPS)
def test_loader_returns_the_same_frames_as_the_two_older_extractors(clip):
    path = require(clip)
    bundle = load_frames(path)
    old_sparse = extract_frames(str(path))
    old_dense = extract_visual_frames(path)

    assert bundle.error is None
    assert len(bundle.sparse) == len(old_sparse.frames)
    assert all(np.array_equal(a, b) for a, b in zip(bundle.sparse, old_sparse.frames))
    assert len(bundle.dense) == len(old_dense.frames)
    assert all(np.array_equal(a, b) for a, b in zip(bundle.dense, old_dense.frames))
    assert bundle.dense_times == pytest.approx(old_dense.timestamps, abs=1e-4)
    assert bundle.dense_indices == old_dense.original_indices
    assert bundle.fps == old_dense.fps


@pytest.mark.parametrize("clip", CLIPS)
def test_timestamps_are_the_containers_real_presentation_times(clip):
    path = require(clip)
    truth = _container_times(path)
    bundle = load_frames(path)

    for t, i in zip(bundle.dense_times, bundle.dense_indices):
        assert t == pytest.approx(truth[i], abs=1e-3)
    for t, i in zip(bundle.sparse_times, bundle.sparse_indices):
        assert t == pytest.approx(truth[i], abs=1e-3)
    assert all(b > a for a, b in zip(bundle.dense_times, bundle.dense_times[1:]))
    assert 5 < bundle.fps < 120, f"fps {bundle.fps} is not a real frame rate"


@pytest.mark.parametrize("clip", CLIPS)
def test_sparse_frames_are_drawn_from_the_dense_set(clip):
    bundle = load_frames(require(clip))

    assert 0 < len(bundle.dense) <= MAX_DENSE_FRAMES
    assert 0 < len(bundle.sparse) <= MAX_SPARSE_FRAMES
    assert len(bundle.sparse) <= len(bundle.dense)
    assert set(bundle.sparse_indices) <= set(bundle.dense_indices)
    expected = [bundle.dense_indices[p] for p in sample_indices(len(bundle.dense_indices), MAX_SPARSE_FRAMES)]
    assert bundle.sparse_indices == expected
    assert bundle.dense[0].ndim == 3 and bundle.dense[0].shape[2] == 3  # RGB


def test_dense_frames_can_be_downscaled_while_sparse_stay_native():
    bundle = load_frames(require(VIDEO_FIXTURES_DIR / "BLINKING.webm"), dense_max_edge=640)

    assert max(bundle.dense[0].shape[:2]) == 640
    assert max(bundle.sparse[0].shape[:2]) == 1920
    assert len(bundle.dense) > len(bundle.sparse)


def test_audio_only_media_returns_an_error_instead_of_hanging():
    """Regression: OpenCV's read() blocked forever on an audio-only container."""
    results = {}

    def run():
        results["bundle"] = load_frames(require(GENUINE_5WORD_WEBM))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=20)

    assert not thread.is_alive(), "frame loading hung on an audio-only file"
    assert results["bundle"].dense == [] and results["bundle"].sparse == []
    assert "video" in results["bundle"].error.lower()


def test_missing_and_garbage_files_never_raise(tmp_path):
    assert load_frames(tmp_path / "nope.webm").error
    junk = tmp_path / "junk.webm"
    junk.write_bytes(b"not a video" * 50)
    assert load_frames(junk).error
