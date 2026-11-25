"""
Tests for the single-decode frame loader (app.media.frames): frame counts and sampling, real
presentation timestamps, the sparse set being drawn from the dense set, downscaling of the dense
frames only, and clean failures on files that are not usable video.
"""
import threading
from pathlib import Path

import av
import numpy as np
import pytest

from app.media.frames import MAX_DENSE_FRAMES, MAX_SPARSE_FRAMES, load_frames
from app.media.sampling import sample_indices
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


def _write_video(path: Path, frame_count: int, fps: int = 30) -> Path:
    """A small synthetic clip whose frame i is a flat grey of brightness 10*i (mod 250)."""
    with av.open(str(path), mode="w", format="mp4") as container:
        stream = container.add_stream("libx264", rate=fps)
        stream.width = stream.height = 64
        stream.pix_fmt = "yuv420p"
        for i in range(frame_count):
            img = np.full((64, 64, 3), (10 * i) % 250, dtype=np.uint8)
            for packet in stream.encode(av.VideoFrame.from_ndarray(img, format="rgb24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


def test_sample_indices():
    assert sample_indices(0, 30) == []
    assert sample_indices(10, 30) == list(range(10))
    assert sample_indices(30, 30) == list(range(30))
    picked = sample_indices(450, 30)
    assert len(picked) == 30 and picked[0] == 0 and picked == sorted(set(picked))
    assert picked[1] == 15


def test_a_short_clip_keeps_every_frame_in_order(tmp_path):
    bundle = load_frames(_write_video(tmp_path / "short.mp4", frame_count=20, fps=30))

    assert bundle.error is None
    assert bundle.dense_indices == list(range(20))
    assert bundle.sparse_indices == list(range(20))
    assert bundle.fps == pytest.approx(30.0, abs=0.5)
    assert bundle.dense_times == pytest.approx([i / 30 for i in range(20)], abs=1e-3)
    # frame k really is frame k (the lossy encoder keeps flat greys close to their value)
    assert [int(f.mean()) for f in bundle.dense] == pytest.approx([(10 * i) % 250 for i in range(20)], abs=12)
    assert bundle.dense[0].shape == (64, 64, 3) and bundle.dense[0].dtype == np.uint8


@pytest.mark.parametrize("frame_count", [45, 300])
def test_a_long_clip_is_sampled_evenly(tmp_path, frame_count):
    bundle = load_frames(_write_video(tmp_path / "long.mp4", frame_count=frame_count))

    assert bundle.dense_indices == sample_indices(frame_count, MAX_DENSE_FRAMES)
    assert bundle.sparse_indices == sample_indices(frame_count, MAX_SPARSE_FRAMES)
    assert len(bundle.sparse) == MAX_SPARSE_FRAMES
    assert len(bundle.dense) == min(frame_count, MAX_DENSE_FRAMES)


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
    empty = tmp_path / "empty.webm"
    empty.write_bytes(b"")
    assert load_frames(empty).error


def test_frames_are_returned_exactly_as_recorded_never_mirrored(tmp_path):
    """
    The direction convention assumes the pipeline never mirrors a frame (see visual/_pose.py).
    The clip is white on its left half and black on its right half, so a hidden flip anywhere
    between the file and the detectors would swap the halves, in the dense and the sparse set.
    """
    path = tmp_path / "left_white.mp4"
    with av.open(str(path), mode="w", format="mp4") as container:
        stream = container.add_stream("libx264", rate=30)
        stream.width = stream.height = 64
        stream.pix_fmt = "yuv420p"
        img = np.zeros((64, 64, 3), dtype=np.uint8)
        img[:, :32] = 255
        for _ in range(10):
            for packet in stream.encode(av.VideoFrame.from_ndarray(img, format="rgb24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)

    bundle = load_frames(path)

    assert bundle.error is None and bundle.dense and bundle.sparse
    for frame in bundle.dense + bundle.sparse:
        assert frame[:, :32].mean() > 200 and frame[:, 32:].mean() < 55

