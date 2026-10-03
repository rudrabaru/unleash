"""
Unit tests for shared frame extraction (Task C / Decision D-19).
Verifies:
1. extract_frames returns RGB frames, fps, error, timestamps, and timestamps_source.
2. Graceful error handling on nonexistent or empty files with timestamps_source="".
3. PyAV path returns timestamps_source="pyav" and exact fps = (N - 1) / duration.
4. Fallback path with AV_AVAILABLE patched to False returns timestamps_source="estimated"
   and len(timestamps) == len(frames).
5. Default 30-frame behavior still holds when max_frames is omitted.
6. Subsampling bounds frames and timestamps to max_frames.
"""
from pathlib import Path

import numpy as np
import pytest

import app.modules.frame_extraction as fe
from app.modules.frame_extraction import (
    FrameExtractionResult,
    extract_frames,
    MAX_FRAMES,
)

try:
    import av
    AV_AVAILABLE = True
except ImportError:  # pragma: no cover
    AV_AVAILABLE = False


def _create_synthetic_video(file_path: Path, frame_count: int = 15, fps: int = 30) -> bool:
    """Create a small synthetic video with distinct timestamps using PyAV."""
    if not AV_AVAILABLE:
        return False
    try:
        container = av.open(str(file_path), mode="w", format="mp4")
        stream = container.add_stream("libx264", rate=fps)
        stream.width = 64
        stream.height = 64
        stream.pix_fmt = "yuv420p"

        for i in range(frame_count):
            img = np.full((64, 64, 3), fill_value=i * (255 // max(frame_count, 1)), dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(img, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)

        for packet in stream.encode():
            container.mux(packet)
        container.close()
        return True
    except Exception:
        return False


def test_extract_frames_nonexistent_file_returns_safe_error():
    result = extract_frames("nonexistent_video_path_12345.webm")
    assert isinstance(result, FrameExtractionResult)
    assert result.frames == []
    assert result.fps == 0.0
    assert result.error is not None
    assert result.timestamps == []
    assert result.timestamps_source == ""


def test_extract_frames_empty_file_returns_safe_error(tmp_path: Path):
    empty_file = tmp_path / "empty.webm"
    empty_file.write_bytes(b"")
    result = extract_frames(str(empty_file))
    assert isinstance(result, FrameExtractionResult)
    assert result.frames == []
    assert result.error is not None
    assert result.timestamps == []
    assert result.timestamps_source == ""


def test_extract_frames_with_synthetic_video(tmp_path: Path):
    if not AV_AVAILABLE:
        pytest.skip("PyAV is not installed in the test environment")

    video_path = tmp_path / "synthetic_test.mp4"
    ok = _create_synthetic_video(video_path, frame_count=20, fps=30)
    if not ok:
        pytest.skip("libx264 encoder is unavailable in PyAV in this environment")

    result = extract_frames(str(video_path), max_frames=10)
    assert isinstance(result, FrameExtractionResult)
    assert result.error is None
    assert len(result.frames) == 10
    assert len(result.timestamps) == 10
    assert result.timestamps_source == "pyav"

    # PyAV fps computation uses (total_count - 1) / duration for inter-frame intervals.
    # 20 frames generated at 30fps span 19 intervals => exactly 30.0 fps.
    assert abs(result.fps - 30.0) < 1.0

    # Frames must be RGB 64x64x3 numpy arrays
    assert result.frames[0].shape == (64, 64, 3)
    assert result.frames[0].dtype == np.uint8

    # Timestamps must be monotonic increasing
    assert result.timestamps[0] >= 0.0
    for i in range(len(result.timestamps) - 1):
        assert result.timestamps[i] <= result.timestamps[i + 1]


def test_extract_frames_fallback_when_av_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    video_path = tmp_path / "synthetic_fallback.mp4"
    ok = _create_synthetic_video(video_path, frame_count=20, fps=30)
    if not ok:
        pytest.skip("libx264 encoder is unavailable in PyAV in this environment")

    # Patch AV_AVAILABLE to False to force OpenCV sequential fallback
    monkeypatch.setattr(fe, "AV_AVAILABLE", False)

    result = extract_frames(str(video_path), max_frames=10)
    assert isinstance(result, FrameExtractionResult)
    assert result.error is None
    assert result.timestamps_source == "estimated"
    assert len(result.frames) == 10
    assert len(result.timestamps) == len(result.frames)
    assert result.fps > 0


def test_extract_frames_default_max_frames_30(tmp_path: Path):
    if not AV_AVAILABLE:
        pytest.skip("PyAV is not installed in the test environment")

    video_path = tmp_path / "synthetic_default_30.mp4"
    ok = _create_synthetic_video(video_path, frame_count=45, fps=30)
    if not ok:
        pytest.skip("libx264 encoder is unavailable in PyAV in this environment")

    # Call with max_frames omitted to test default parameter (MAX_FRAMES = 30)
    result = extract_frames(str(video_path))
    assert len(result.frames) == 30
    assert len(result.timestamps) == 30
    assert result.timestamps_source == "pyav"


def test_subsampling_respects_max_frames(tmp_path: Path):
    if not AV_AVAILABLE:
        pytest.skip("PyAV is not installed in the test environment")

    video_path = tmp_path / "synthetic_subsample.mp4"
    ok = _create_synthetic_video(video_path, frame_count=45, fps=30)
    if not ok:
        pytest.skip("libx264 encoder is unavailable in PyAV in this environment")

    result = extract_frames(str(video_path), max_frames=MAX_FRAMES)
    assert len(result.frames) == MAX_FRAMES
    assert len(result.timestamps) == MAX_FRAMES
