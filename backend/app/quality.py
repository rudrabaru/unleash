"""
What can be said about a recording before, and apart from, judging the person in it.

Three different outcomes come from here, and they must not be confused:

  * An upload that is refused at the door (`upload_rejection`, `submitted_too_early`): it cannot be a
    recording of this protocol at all (unreadable, far too long, an enormous picture, back before the
    recording could have finished). The session is left unused, so the person can try again.
  * A capture problem (`recording_problem`, `capture_problem_in`): the recording is readable but not
    good enough to judge (too short, no face in the first seconds, a dead microphone, picture and
    sound that do not line up). The result is `RETRY`, never `FAILED`: nothing was shown to be wrong
    with the person, and nothing is accepted either.
  * Everything else is judged by the detectors and fused.

Nothing here accepts anyone; `RETRY` is a refusal that asks for another go with a new challenge.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from app.media.probe import MediaProbe
from app.protocol import PhaseWindows
from app.schemas.detector import DetectorResult

# A recording of this protocol is about 13 s. Anything past this is not one, and is cut short when read.
HARD_MAX_SECONDS = 30.0
# Largest picture accepted, in either orientation (1920x1080 or 1080x1920). A bigger frame costs
# memory out of proportion to anything the detectors can use.
MAX_LONG_EDGE = 1920
MAX_SHORT_EDGE = 1080
# Picture and sound start together in a real recording; further apart than this, the audio windows
# and the video windows cannot be trusted to name the same moments.
MAX_AV_START_SKEW_SECONDS = 0.5


@dataclass(frozen=True)
class CaptureProblem:
    code: str  # machine-readable, for the interface to turn into plain words
    reason: str


def upload_rejection(probe: MediaProbe) -> Optional[str]:
    """Why a probed upload is refused at the door, or None. The probe should have been read with HARD_MAX_SECONDS."""
    if probe.error:
        return "The recording could not be read. Please record again."
    if probe.over_limit:
        return f"The recording is longer than {HARD_MAX_SECONDS:.0f} seconds."
    if probe.width and probe.height and (
        max(probe.width, probe.height) > MAX_LONG_EDGE or min(probe.width, probe.height) > MAX_SHORT_EDGE
    ):
        return f"The picture is larger than {MAX_LONG_EDGE}x{MAX_SHORT_EDGE}."
    return None


def submitted_too_early(created_at: datetime, now: datetime, minimum_seconds: float) -> Optional[str]:
    """
    A recording of the protocol cannot be finished and uploaded sooner than its own length after the
    session started. An upload that arrives sooner was not made for this session. (A script can wait
    out the time, so this only stops the careless; it costs nothing.)
    """
    if minimum_seconds > 0 and (now - created_at).total_seconds() < minimum_seconds:
        return "The recording arrived before it could have been made. Please record again."
    return None


def recording_problem(probe: MediaProbe, phases: Optional[PhaseWindows]) -> Optional[CaptureProblem]:
    """A capture problem visible from the timeline alone, so no detector has to run to find it."""
    if probe.over_limit:
        return CaptureProblem("too_long", f"The recording is longer than {HARD_MAX_SECONDS:.0f} seconds.")
    rejection = upload_rejection(probe)
    if rejection and not probe.error:
        return CaptureProblem("too_large", rejection)
    if phases is None or probe.duration is None:
        return None
    if probe.duration < phases.min_recording_seconds:
        return CaptureProblem(
            "too_short",
            f"The recording is {probe.duration:.1f} s long; it needs about {phases.total_seconds:.0f} s.",
        )
    if probe.video and probe.audio and abs(probe.video.first - probe.audio.first) > MAX_AV_START_SKEW_SECONDS:
        return CaptureProblem("av_skew", "The picture and the sound of the recording do not start together.")
    return None


def capture_problem_in(signals: Dict[str, DetectorResult]) -> Optional[CaptureProblem]:
    """A capture problem a detector found while judging: no face to measure, or a microphone that recorded nothing."""
    challenge = signals.get("visual_challenge")
    code = ((challenge.details or {}).get("failure_code") if challenge else None)
    if code == "bad_baseline":
        return CaptureProblem(code, "A steady face looking at the camera was not seen at the start of the recording.")
    if code == "no_face":
        return CaptureProblem(code, "The face was not seen for long enough while the movement was asked.")
    audio = signals.get("audio_pipeline")
    if audio and (audio.details or {}).get("failure_code") == "mic_silent":
        return CaptureProblem("mic_silent", "The microphone recorded only silence.")
    return None
