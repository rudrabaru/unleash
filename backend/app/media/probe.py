"""
Look at a recording's timeline without decoding it: when its video and audio start and end, and
how large the picture is. Only packets are read (milliseconds, no decoding), so this is safe to run
on an upload before any expensive step.

`recording_start` is the zero of the recording's own clock. The phase windows (app/protocol.py) are
offsets from it. The browser starts its timer when the recorder starts, so the earliest thing in the
file, whichever track it is on, is the closest match for that moment.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import av


@dataclass(frozen=True)
class StreamTimes:
    first: float  # presentation time of the first packet, seconds on the container clock
    last: float  # end of the last packet read


@dataclass(frozen=True)
class MediaProbe:
    video: Optional[StreamTimes] = None
    audio: Optional[StreamTimes] = None
    width: Optional[int] = None
    height: Optional[int] = None
    # True when reading stopped early because a track ran past the limit that was asked for
    over_limit: bool = False
    error: Optional[str] = None

    @property
    def recording_start(self) -> Optional[float]:
        """Zero of the recording's clock: the earliest packet of either track, never below 0."""
        firsts = [t.first for t in (self.video, self.audio) if t is not None]
        return max(0.0, min(firsts)) if firsts else None

    @property
    def duration(self) -> Optional[float]:
        """Seconds from the recording's start to the end of its last packet."""
        lasts = [t.last for t in (self.video, self.audio) if t is not None]
        start = self.recording_start
        return max(lasts) - start if lasts and start is not None else None


def probe_streams(source: Union[str, Path], limit_seconds: Optional[float] = None) -> MediaProbe:
    """
    Read the packet timeline of `source`. With `limit_seconds` the read stops as soon as a packet
    ends later than that on the container clock and the result says `over_limit`, so a hostile file
    that claims hours costs a few milliseconds, not hours. Never raises.
    """
    try:
        with av.open(str(source)) as container:
            video_stream = container.streams.video[0] if container.streams.video else None
            audio_stream = container.streams.audio[0] if container.streams.audio else None
            if video_stream is None and audio_stream is None:
                return MediaProbe(error="No audio or video stream in media file.")
            width = video_stream.codec_context.width if video_stream else None
            height = video_stream.codec_context.height if video_stream else None

            seen = {}  # stream index -> [first, last]
            over_limit = False
            for packet in container.demux(*(s for s in (video_stream, audio_stream) if s is not None)):
                if packet.pts is None or not packet.size:
                    continue
                start = float(packet.pts * packet.time_base)
                end = start + float(packet.duration * packet.time_base) if packet.duration else start
                times = seen.setdefault(packet.stream.index, [start, end])
                times[0], times[1] = min(times[0], start), max(times[1], end)
                if limit_seconds is not None and end > limit_seconds:
                    over_limit = True
                    break

            def times_of(stream) -> Optional[StreamTimes]:
                found = seen.get(stream.index) if stream is not None else None
                return StreamTimes(first=found[0], last=found[1]) if found else None

            return MediaProbe(
                video=times_of(video_stream),
                audio=times_of(audio_stream),
                width=width or None,
                height=height or None,
                over_limit=over_limit,
            )
    except Exception as exc:  # noqa: BLE001 - a probe must never raise to the caller
        return MediaProbe(error=f"Could not read the media timeline: {exc}")
