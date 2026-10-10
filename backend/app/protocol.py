"""
The challenge protocol: how one recording is divided into phases.

A recording is three phases on its own clock (seconds from its start):

  * read  - the words are shown and the person faces the camera; nothing is scored. The head
            pose measured here is the person's own neutral baseline.
  * speak - the person says the words, which are still on screen.
  * act   - the words are hidden and the head action is cued: turn, hold, return to centre.

The server owns these numbers. `POST /sessions` sends them to the browser, which draws its timers
from them, and the detectors read the same object, so what the person is told to do and what is
judged cannot drift apart. The server's wall clock plays no part: the browser creates the session
and then starts the recorder, so every window is an offset on the recording itself.
"""
from dataclasses import dataclass
from typing import Optional, Tuple

PROTOCOL_VERSION = 1

# A recording shorter or longer than this is not a response to this protocol. The bounds are
# enforced where the upload arrives (package P1-C); they live here so the browser can show them.
MIN_RECORDING_SECONDS = 12.0
MAX_RECORDING_SECONDS = 16.0

# The recorder starts a little after the on-screen timer, so a phase edge on the recording is
# not exactly where the screen changed. Detectors widen a window by this much on each side before
# judging what happens inside it. A starting value: it is set from the pilot recordings (the
# on-screen flash and beep at t=3 s and t=8 s against where they land in the file).
WINDOW_GUARD_SECONDS = 0.4


@dataclass(frozen=True)
class Phase:
    name: str
    start: float
    end: float


@dataclass(frozen=True)
class PhaseWindows:
    version: int
    phases: Tuple[Phase, ...]
    min_recording_seconds: float
    max_recording_seconds: float

    @property
    def total_seconds(self) -> float:
        return self.phases[-1].end

    def phase(self, name: str) -> Phase:
        for phase in self.phases:
            if phase.name == name:
                return phase
        raise KeyError(f"unknown phase '{name}'")

    def window(self, name: str, before: float = 0.0, after: float = 0.0) -> Tuple[float, float]:
        """(start, end) of a phase in recording seconds, widened by `before` and `after` and never before 0."""
        phase = self.phase(name)
        return max(0.0, phase.start - before), phase.end + after

    def phase_at(self, seconds: float) -> Optional[str]:
        """The phase a moment on the recording falls in, or None before the start and after the end."""
        for phase in self.phases:
            if phase.start <= seconds < phase.end:
                return phase.name
        return None


PROTOCOL_V1 = PhaseWindows(
    version=PROTOCOL_VERSION,
    phases=(Phase("read", 0.0, 3.0), Phase("speak", 3.0, 8.0), Phase("act", 8.0, 13.0)),
    min_recording_seconds=MIN_RECORDING_SECONDS,
    max_recording_seconds=MAX_RECORDING_SECONDS,
)
