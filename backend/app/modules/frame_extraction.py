"""
Shared frame extraction utility used by the visual and antispoof modules.

Per docs/unleash_team_companion_guide.md Section 2.5: accepts a .webm path, samples
up to 30 frames from the video, returns RGB frames + fps. Handles empty/corrupt/short
files without raising.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

try:
    import av
    AV_AVAILABLE = True
except ImportError:  # pragma: no cover
    AV_AVAILABLE = False

MAX_FRAMES = 30


@dataclass
class FrameExtractionResult:
    frames: List[np.ndarray]  # RGB, HxWx3
    fps: float
    error: str | None = None
    timestamps: List[float] = field(default_factory=list)  # Presentation time in seconds
    timestamps_source: str = ""  # "pyav", "estimated", or "" on error


def _extract_via_pyav(video_path: str, max_frames: int, hard_cap: int = 2000) -> Optional[FrameExtractionResult]:
    """Decode frames and exact presentation timestamps using PyAV (Decision D-19)."""
    if not AV_AVAILABLE:
        return None
    try:
        container = av.open(video_path)
        if not container.streams.video:
            container.close()
            return None
        stream = container.streams.video[0]

        all_timestamps: List[Optional[float]] = []
        all_had_pts = True

        # Pass 1: count frames and read their real times. No RGB conversion yet: converting
        # every frame to keep only ~30 was the slowest part of this function.
        for frame in container.decode(video=0):
            if len(all_timestamps) >= hard_cap:
                break
            if frame.time is not None:
                ts = float(frame.time)
            elif frame.pts is not None and stream.time_base is not None:
                ts = float(frame.pts * stream.time_base)
            else:
                all_had_pts = False  # no real time for this frame: never invent one (J5)
                ts = None
            all_timestamps.append(None if ts is None else round(ts, 4))

        if not all_timestamps:
            container.close()
            return None

        total_count = len(all_timestamps)
        real_times = [t for t in all_timestamps if t is not None]
        duration = real_times[-1] - real_times[0] if len(real_times) > 1 else 0.0
        # For N frames from t_0 to t_{N-1}, duration covers N-1 inter-frame intervals
        if duration > 0.1:
            fps = round(float((total_count - 1) / duration), 2)
        elif stream.average_rate and float(stream.average_rate) > 0:
            fps = round(float(stream.average_rate), 2)
        else:
            fps = 30.0

        indices = _sample_indices(total_count, max_frames)

        # Pass 2: decode again, converting only the sampled frames to RGB.
        wanted = set(indices)
        kept = {}
        container.seek(0)
        for index, frame in enumerate(container.decode(container.streams.video[0])):
            if index >= total_count:
                break
            if index in wanted:
                kept[index] = frame.to_ndarray(format="rgb24")
        container.close()
        if len(kept) != len(indices):
            return None  # pass 2 did not reproduce pass 1; let the OpenCV path handle the file

        sampled_frames = [kept[i] for i in indices]
        # Either every sampled frame carries its real PyAV time, or none are reported.
        sampled_timestamps = [all_timestamps[i] for i in indices] if all_had_pts else []
        timestamps_source = "pyav" if all_had_pts else ""

        return FrameExtractionResult(
            frames=sampled_frames,
            fps=fps,
            error=None,
            timestamps=sampled_timestamps,
            timestamps_source=timestamps_source,
        )
    except Exception:
        return None


def _has_video_stream(video_path: str) -> bool:
    """OpenCV's `cap.read()` blocks forever on an audio-only container, so check first."""
    if not AV_AVAILABLE:
        return True
    try:
        with av.open(video_path) as container:
            return bool(container.streams.video)
    except Exception:  # noqa: BLE001 - let the OpenCV path report the open failure as before
        return True


def extract_frames(video_path: str, max_frames: int = MAX_FRAMES) -> FrameExtractionResult:
    if not _has_video_stream(video_path):
        return FrameExtractionResult(frames=[], fps=0.0, error="No video stream in media file.")

    # 1. Primary path: PyAV for real presentation timestamps (D-19)
    pyav_result = _extract_via_pyav(video_path, max_frames)
    if pyav_result is not None:
        return pyav_result

    logger.warning("PyAV unavailable or failed for %s; falling back to OpenCV sequential extraction", video_path)

    # 2. Fallback path: OpenCV sequential reading if PyAV is unavailable or fails
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        cap.release()
        return FrameExtractionResult(frames=[], fps=0.0, error=f"Could not open video: {video_path}", timestamps=[], timestamps_source="")

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
            return FrameExtractionResult(frames=[], fps=fps, error="No frames could be decoded from video.", timestamps=[], timestamps_source="")

        total_count = len(all_frames_bgr)
        indices = _sample_indices(total_count, max_frames)
        sampled = [all_frames_bgr[i] for i in indices]
        frames = [cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB) for frame_bgr in sampled]
        timestamps = [round(i / fps, 4) for i in indices]

        return FrameExtractionResult(frames=frames, fps=fps, error=None, timestamps=timestamps, timestamps_source="estimated")
    except Exception as exc:  # noqa: BLE001 - must never raise to caller
        return FrameExtractionResult(frames=[], fps=0.0, error=f"Frame extraction failed: {exc}", timestamps=[], timestamps_source="")
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
