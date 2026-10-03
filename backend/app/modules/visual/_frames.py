"""
Dense frame extraction utility for visual liveness and challenge compliance (B6).

MediaRecorder WebM clips typically run at ~30 fps. Standard anti-spoof detectors
only require 30 frames per clip (0.5s gaps), but human eye blinks last only
0.1s - 0.3s. Dense sampling (up to 120 frames / ~8-10 fps) ensures blinks,
micro-movements, and quick head turns are reliably captured without missing
critical 100-300ms transitions.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union

import cv2
import numpy as np

MAX_VISUAL_FRAMES = 120


@dataclass
class VisualFramesResult:
    frames: List[np.ndarray]  # RGB, HxWx3
    fps: float
    timestamps: List[float]  # Presentation time in seconds
    original_indices: List[int]  # Indices in the raw video stream
    error: Optional[str] = None


def extract_visual_frames(
    video_source: Union[str, Path],
    max_frames: int = MAX_VISUAL_FRAMES,
) -> VisualFramesResult:
    """
    Densely extract up to `max_frames` RGB frames and real presentation timestamps.
    Handles corrupt/missing/short video files gracefully without raising.
    """
    video_path = str(video_source)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        cap.release()
        return VisualFramesResult(
            frames=[],
            fps=0.0,
            timestamps=[],
            original_indices=[],
            error=f"Could not open video file: {video_path}",
        )

    try:
        raw_fps = cap.get(cv2.CAP_PROP_FPS)

        # Decode frames sequentially to avoid OpenCV WebM seek issues
        all_frames_bgr, all_timestamps = _read_all_frames_sequential(cap)
        if not all_frames_bgr:
            return VisualFramesResult(
                frames=[],
                fps=raw_fps or 30.0,
                timestamps=[],
                original_indices=[],
                error="No frames could be decoded from video.",
            )

        total_count = len(all_frames_bgr)
        duration = all_timestamps[-1] - all_timestamps[0] if len(all_timestamps) > 1 else 0.0

        # Derive realistic fps (MediaRecorder often reports 1000 fps)
        if raw_fps and 1.0 <= raw_fps <= 120.0 and raw_fps != 1000.0:
            fps = float(raw_fps)
        elif duration > 0.1:
            fps = round(float(total_count / duration), 2)
        else:
            fps = 30.0

        # If timestamps were missing (all 0), derive from sequence index and fps
        if all(ts == 0.0 for ts in all_timestamps[1:]):
            all_timestamps = [round(i / fps, 4) for i in range(total_count)]

        indices = _sample_indices(total_count, max_frames)
        sampled_frames = [cv2.cvtColor(all_frames_bgr[i], cv2.COLOR_BGR2RGB) for i in indices]
        sampled_timestamps = [all_timestamps[i] for i in indices]

        return VisualFramesResult(
            frames=sampled_frames,
            fps=fps,
            timestamps=sampled_timestamps,
            original_indices=indices,
            error=None,
        )
    except Exception as exc:  # noqa: BLE001 - must never raise to caller
        return VisualFramesResult(
            frames=[],
            fps=0.0,
            timestamps=[],
            original_indices=[],
            error=f"Visual frame extraction failed: {exc}",
        )
    finally:
        cap.release()


def _read_all_frames_sequential(
    cap: cv2.VideoCapture,
    hard_cap: int = 2000,
) -> Tuple[List[np.ndarray], List[float]]:
    """Decode frames sequentially and record presentation timestamp in seconds."""
    frames = []
    timestamps = []
    while len(frames) < hard_cap:
        msec = cap.get(cv2.CAP_PROP_POS_MSEC)
        ok, frame_bgr = cap.read()
        if not ok or frame_bgr is None:
            break
        frames.append(frame_bgr)
        timestamps.append(max(0.0, float(msec / 1000.0)) if msec >= 0 else 0.0)
    return frames, timestamps


def _sample_indices(total_frames: int, max_frames: int) -> List[int]:
    """Evenly subsample frame indices up to max_frames."""
    if total_frames <= max_frames:
        return list(range(total_frames))
    step = total_frames / max_frames
    return [int(i * step) for i in range(max_frames)]
