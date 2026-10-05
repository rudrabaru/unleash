"""
Decode a recording once and hand every video detector the frames it needs.

Two sets come out of one decode pass:
  * dense  - up to 120 evenly spaced frames, each with its real presentation time. The visual
             detectors need them: a blink lasts only 0.1-0.3 s.
  * sparse - up to 30 frames drawn evenly from the dense set, at native resolution. The
             deepfake and replay detectors use them (replay moire depends on resolution).

Timestamps come from the container through PyAV (browser recordings report a bogus 1000 fps
through OpenCV and carry no seek index). A frame without a real timestamp is dropped; a time
is never invented. Frames are counted by demuxing packets only (milliseconds), then decoded
once, converting only the frames that are kept, so memory stays small.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set, Union

import av
import numpy as np

from app.media.sampling import sample_indices

logger = logging.getLogger(__name__)

MAX_DENSE_FRAMES = 120
MAX_SPARSE_FRAMES = 30
# A challenge response is about 15 s; decoding stops here (about 66 s at 30 fps) on a longer file.
MAX_DECODED_FRAMES = 2000
# Long-edge cap for the dense frames. Webcam recordings (up to 1280x720) are not touched; larger
# inputs are downscaled, which bounds the 120 held RGB frames at about 330 MB instead of about
# 750 MB for 1080p. MediaPipe takes the same ~10 ms per frame at either size. Downscaling is not
# perfectly score-neutral: on the 1080p sample clips the liveness score moved by up to 0.02.
DENSE_MAX_EDGE = 1280


@dataclass
class FrameBundle:
    dense: List[np.ndarray] = field(default_factory=list)  # RGB, HxWx3
    dense_times: List[float] = field(default_factory=list)  # seconds, same clock as the audio
    dense_indices: List[int] = field(default_factory=list)  # position of each frame in the decoded stream
    sparse: List[np.ndarray] = field(default_factory=list)  # RGB, native resolution
    sparse_times: List[float] = field(default_factory=list)
    sparse_indices: List[int] = field(default_factory=list)
    fps: float = 0.0  # average real frame rate (decoded frames / clip duration); informational
    error: Optional[str] = None


def _failure(error: str) -> FrameBundle:
    return FrameBundle(error=error)


def _count_frames(path: str) -> int:
    """Number of video frames, found by demuxing packets only (no decoding)."""
    with av.open(path) as container:
        stream = container.streams.video[0]
        count = 0
        for packet in container.demux(stream):
            if packet.size:  # the final flush packet is empty
                count += 1
                if count >= MAX_DECODED_FRAMES:
                    break
        return count


def _scaled_size(width: int, height: int, max_edge: Optional[int]) -> Optional[tuple]:
    """Target (width, height) when the long edge exceeds `max_edge`, else None (keep native)."""
    if not max_edge or max(width, height) <= max_edge:
        return None
    factor = max_edge / max(width, height)
    return max(2, round(width * factor)), max(2, round(height * factor))


@dataclass
class _Decoded:
    frames: int = 0  # frames decoded
    timed: int = 0  # frames that carry a real timestamp
    first_time: Optional[float] = None
    last_time: Optional[float] = None
    kept: dict = field(default_factory=dict)  # index -> (time, native_rgb, dense_rgb)


def _decode(path: str, total: int, dense_ids: List[int], sparse_ids: Set[int], max_edge: Optional[int]) -> _Decoded:
    """One decode pass over the first `total` frames, converting only the frames that are kept."""
    wanted_dense = set(dense_ids)
    out = _Decoded()
    with av.open(path) as container:
        stream = container.streams.video[0]
        for index, frame in enumerate(container.decode(stream)):
            if index >= total:
                break
            out.frames = index + 1
            if frame.time is not None:
                out.timed += 1
                out.first_time = float(frame.time) if out.first_time is None else out.first_time
                out.last_time = float(frame.time)
            in_dense, in_sparse = index in wanted_dense, index in sparse_ids
            if not (in_dense or in_sparse) or frame.time is None:
                continue
            size = _scaled_size(frame.width, frame.height, max_edge)
            native = frame.to_ndarray(format="rgb24") if (in_sparse or (in_dense and size is None)) else None
            if in_dense:
                dense = native if size is None else frame.reformat(width=size[0], height=size[1], format="rgb24").to_ndarray()
            else:
                dense = None
            out.kept[index] = (round(float(frame.time), 4), native, dense)
    return out


def load_frames(video_source: Union[str, Path], dense_max_edge: Optional[int] = None) -> FrameBundle:
    """
    Decode `video_source` once. `dense_max_edge` downscales the dense frames so their long edge
    is at most that many pixels; the sparse frames always stay native. Never raises: a missing,
    corrupt or audio-only file returns a bundle with `error` set and no frames.
    """
    path = str(video_source)
    try:
        with av.open(path) as container:
            if not container.streams.video:
                return _failure("No video stream in media file.")
    except Exception as exc:  # noqa: BLE001 - must never raise to the caller
        return _failure(f"Could not open video file: {exc}")

    try:
        total = _count_frames(path)
        if total == 0:
            return _failure("No frames could be decoded from video.")
        dense_ids = sample_indices(total, MAX_DENSE_FRAMES)
        sparse_ids = [dense_ids[p] for p in sample_indices(len(dense_ids), MAX_SPARSE_FRAMES)]

        decoded = _decode(path, total, dense_ids, set(sparse_ids), dense_max_edge)
        if decoded.frames != total:
            # The packet count and the decoder disagree (rare): redo the selection with the
            # real count, by decoding again from a fresh container (never by seeking back).
            logger.warning("Packet count %d != decoded frames %d for %s; selecting again", total, decoded.frames, path)
            total = decoded.frames
            dense_ids = sample_indices(total, MAX_DENSE_FRAMES)
            sparse_ids = [dense_ids[p] for p in sample_indices(len(dense_ids), MAX_SPARSE_FRAMES)]
            decoded = _decode(path, total, dense_ids, set(sparse_ids), dense_max_edge)

        kept = decoded.kept
        dense_ids = [i for i in dense_ids if i in kept and kept[i][2] is not None]
        sparse_ids = [i for i in sparse_ids if i in kept and kept[i][1] is not None]
        if not dense_ids:
            return _failure("No timestamped frames could be decoded from video.")

        times = [kept[i][0] for i in dense_ids]
        duration = (decoded.last_time - decoded.first_time) if decoded.timed > 1 else 0.0
        fps = round((decoded.timed - 1) / duration, 2) if duration > 0 else 0.0

        return FrameBundle(
            dense=[kept[i][2] for i in dense_ids],
            dense_times=times,
            dense_indices=dense_ids,
            sparse=[kept[i][1] for i in sparse_ids],
            sparse_times=[kept[i][0] for i in sparse_ids],
            sparse_indices=sparse_ids,
            fps=fps,
        )
    except Exception as exc:  # noqa: BLE001 - must never raise to the caller
        return _failure(f"Frame extraction failed: {exc}")
