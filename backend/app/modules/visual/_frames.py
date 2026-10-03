"""
Dense frame extraction with real timestamps for visual liveness, challenge compliance and the
Stage 4 lip series (B6 dense sampling, B4 `time_seconds`; decision D-19).

Why PyAV: browser MediaRecorder `.webm` reports a bogus 1000 fps through OpenCV and carries no
seek index, so OpenCV's clock is unreliable. PyAV reads each frame's real presentation
timestamp straight from the container.

Blinks last ~0.1-0.3 s, so the visual consumers need far more than the 30 frames the
deepfake/replay detectors use (0.5 s gaps). Up to MAX_VISUAL_FRAMES (120, ~8 fps over a 15 s
clip) are returned. Only the sampled frames are converted to RGB, so memory stays small.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

import av
import numpy as np

MAX_VISUAL_FRAMES = 120


@dataclass
class VisualFramesResult:
    frames: List[np.ndarray]  # RGB, HxWx3
    fps: float  # average real frame rate (decoded frames / clip duration); informational
    timestamps: List[float]  # real presentation time in seconds of each returned frame
    original_indices: List[int]  # index of each returned frame in the decoded video stream
    error: Optional[str] = None


def _failure(error: str) -> VisualFramesResult:
    return VisualFramesResult(frames=[], fps=0.0, timestamps=[], original_indices=[], error=error)


def _sample_indices(total_frames: int, max_frames: int) -> List[int]:
    """Evenly subsample frame indices up to max_frames."""
    if total_frames <= max_frames:
        return list(range(total_frames))
    step = total_frames / max_frames
    return [int(i * step) for i in range(max_frames)]


def _frame_time(frame: "av.VideoFrame") -> Optional[float]:
    return float(frame.time) if frame.time is not None else None


def _decode(container: "av.container.InputContainer", stream, wanted: Optional[set]):
    """Decode sequentially. Returns (all_times, kept) where kept maps index -> (rgb, time).
    With wanted=None only timestamps are collected (no RGB conversion)."""
    times: List[Optional[float]] = []
    kept = {}
    for index, frame in enumerate(container.decode(stream)):
        t = _frame_time(frame)
        times.append(t)
        if wanted is not None and index in wanted:
            kept[index] = (frame.to_ndarray(format="rgb24"), t)
    return times, kept


def extract_visual_frames(
    video_source: Union[str, Path],
    max_frames: int = MAX_VISUAL_FRAMES,
) -> VisualFramesResult:
    """
    Densely extract up to `max_frames` RGB frames with their real presentation timestamps.
    Never raises; a file with no video stream, a corrupt file or an unreadable one returns
    `error` set and no frames.
    """
    try:
        container = av.open(str(video_source))
    except Exception as exc:  # noqa: BLE001 - must never raise to caller
        return _failure(f"Could not open video file: {exc}")

    try:
        if not container.streams.video:
            return _failure("No video stream in media file.")
        stream = container.streams.video[0]

        # Pass 1: count frames and read their real timestamps (no RGB conversion).
        times, _ = _decode(container, stream, wanted=None)
        if not times:
            return _failure("No frames could be decoded from video.")
        indices = _sample_indices(len(times), max_frames)

        # Pass 2: decode again, converting only the sampled frames.
        container.seek(0)
        _, kept = _decode(container, container.streams.video[0], wanted=set(indices))
        indices = [i for i in indices if i in kept and times[i] is not None]
        if not indices:
            return _failure("No timestamped frames could be decoded from video.")

        valid_times = [t for t in times if t is not None]
        duration = valid_times[-1] - valid_times[0] if len(valid_times) > 1 else 0.0
        fps = round((len(valid_times) - 1) / duration, 2) if duration > 0 else 0.0

        return VisualFramesResult(
            frames=[kept[i][0] for i in indices],
            fps=fps,
            timestamps=[round(times[i], 4) for i in indices],
            original_indices=indices,
        )
    except Exception as exc:  # noqa: BLE001 - must never raise to caller
        return _failure(f"Visual frame extraction failed: {exc}")
    finally:
        container.close()
