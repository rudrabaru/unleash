"""
Shared frame extraction utility used by the visual and antispoof modules.

Per docs/unleash_team_companion_guide.md Section 2.5: accepts a .webm path, samples
up to 30 frames from the video, returns RGB frames + fps. Handles empty/corrupt/short
files without raising.
"""
from dataclasses import dataclass
from typing import List

import av
import cv2
import numpy as np

MAX_FRAMES = 30


@dataclass
class FrameExtractionResult:
    frames: List[np.ndarray]  # RGB, HxWx3
    fps: float
    error: str | None = None


def _has_video_stream(video_path: str) -> bool:
    """OpenCV's `cap.read()` blocks forever on an audio-only container, so check first."""
    try:
        with av.open(video_path) as container:
            return bool(container.streams.video)
    except Exception:  # noqa: BLE001 - let the OpenCV path report the open failure as before
        return True


def extract_frames(video_path: str, max_frames: int = MAX_FRAMES) -> FrameExtractionResult:
    if not _has_video_stream(video_path):
        return FrameExtractionResult(frames=[], fps=0.0, error="No video stream in media file.")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        cap.release()
        return FrameExtractionResult(frames=[], fps=0.0, error=f"Could not open video: {video_path}")

    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not fps or fps <= 0:
            fps = 30.0  # sensible default when the container omits fps metadata

        # CAP_PROP_FRAME_COUNT is unreliable for MediaRecorder-produced .webm:
        # some VP8/Opus containers lack a seek index, so OpenCV's FFmpeg backend
        # falls back to fps * duration using a bogus fps, wildly overstating the
        # real frame count. Seeking to those bogus indices then silently fails,
        # decoding only frame 0. These clips are short (~15s), so decode all
        # frames sequentially and subsample the real list instead of trusting
        # metadata-based seeks.
        all_frames_bgr = _read_all_frames_sequential(cap)

        if not all_frames_bgr:
            return FrameExtractionResult(frames=[], fps=fps, error="No frames could be decoded from video.")

        sampled = _subsample(all_frames_bgr, max_frames)
        frames = [cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB) for frame_bgr in sampled]

        return FrameExtractionResult(frames=frames, fps=fps, error=None)
    except Exception as exc:  # noqa: BLE001 - must never raise to caller
        return FrameExtractionResult(frames=[], fps=0.0, error=f"Frame extraction failed: {exc}")
    finally:
        cap.release()


def _read_all_frames_sequential(cap: cv2.VideoCapture, hard_cap: int = 2000) -> List[np.ndarray]:
    """Decode every frame in sequence. `hard_cap` bounds memory on a malformed/huge file."""
    frames = []
    while len(frames) < hard_cap:
        ok, frame_bgr = cap.read()
        if not ok or frame_bgr is None:
            break
        frames.append(frame_bgr)
    return frames


def _subsample(frames: List[np.ndarray], max_frames: int) -> List[np.ndarray]:
    if len(frames) <= max_frames:
        return frames
    indices = _sample_indices(len(frames), max_frames)
    return [frames[i] for i in indices]


def _sample_indices(total_frames: int, max_frames: int) -> List[int]:
    if total_frames <= max_frames:
        return list(range(total_frames))
    step = total_frames / max_frames
    return [int(i * step) for i in range(max_frames)]
