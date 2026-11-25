"""
Phase-aware head-action check (turn, hold, return), used when the analysis is given the protocol
windows (app/protocol.py). It replaces the whole-recording check for sessions:

  * Baseline - the person's own neutral pose, measured in the Read window only.
  * Action   - judged in the Act window only (widened by the window guard), so a nod or a turn while
               speaking, or at any other time, counts for nothing.
  * Excursion - at least max(15 deg yaw / 10 deg pitch, 5 x the baseline jitter) toward the asked
               direction, held for at least 0.4 s (by timestamps, not frame counts).
  * Return   - back to within max(8 / 6 deg, 3 x the baseline jitter) of the baseline for at least
               0.2 s before the window ends.

Each failure has a code (`no_face`, `bad_baseline`, `no_motion`, `wrong_direction`, `no_hold`,
`no_return`) so the caller can tell a capture problem from a missed action. Directions follow the
convention in `_pose.py` (an unmirrored feed: your own left is positive yaw). The numbers below are
starting values; the pilot recordings confirm them.
"""
import statistics
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.modules.visual._pose import PITCH_THRESHOLD, YAW_THRESHOLD, _blink_twice
from app.protocol import WINDOW_GUARD_SECONDS, PhaseWindows
from app.schemas.session import VisualChallengeType

# Baseline: the Read window without its first moments (the person is still settling) and without
# its last moments (the next phase may already have started on the recording).
BASELINE_SKIP_START_SECONDS = 0.5
BASELINE_SKIP_END_SECONDS = 0.3
MIN_BASELINE_FRAMES = 8
# A neutral pose is roughly facing the camera; beyond this the person was not looking at it in Read.
MAX_BASELINE_YAW_DEG = 20.0
MAX_BASELINE_PITCH_DEG = 25.0
SIGMA_FLOOR_DEG = 1.0  # a very steady baseline must not make the threshold vanishingly small

EXCURSION_SIGMAS = 5.0
RETURN_SIGMAS = 3.0
YAW_RETURN_DEG = 8.0
PITCH_RETURN_DEG = 6.0
MIN_HOLD_SECONDS = 0.4
MIN_RETURN_SECONDS = 0.2
MAX_GAP_SECONDS = 0.3  # a face lost for no longer than this does not break a hold or a return
MIN_ACT_FACE_FRAMES = 5


@dataclass(frozen=True)
class _Axis:
    key: str  # "yaw" or "pitch"
    sign: float  # +1 when the asked direction is a positive change of that angle, else -1
    threshold_floor: float
    return_floor: float


_AXES = {
    VisualChallengeType.TURN_HEAD_LEFT: _Axis("yaw", 1.0, YAW_THRESHOLD, YAW_RETURN_DEG),
    VisualChallengeType.TURN_HEAD_RIGHT: _Axis("yaw", -1.0, YAW_THRESHOLD, YAW_RETURN_DEG),
    VisualChallengeType.LOOK_DOWN: _Axis("pitch", 1.0, PITCH_THRESHOLD, PITCH_RETURN_DEG),
    VisualChallengeType.LOOK_UP: _Axis("pitch", -1.0, PITCH_THRESHOLD, PITCH_RETURN_DEG),
}


@dataclass(frozen=True)
class _Sample:
    t: float  # seconds from the recording start
    yaw: float
    pitch: float


@dataclass(frozen=True)
class _Baseline:
    yaw: float
    pitch: float
    sigma_yaw: float
    sigma_pitch: float


def _timed_samples(frames: List[Dict[str, Any]], recording_start: float) -> List[_Sample]:
    """Frames that have both a timestamp and a measured head pose, placed on the recording's clock."""
    return [
        _Sample(float(f["time_seconds"]) - recording_start, f["yaw"], f["pitch"])
        for f in frames
        if f.get("time_seconds") is not None and f.get("yaw") is not None and f.get("pitch") is not None
    ]


def _robust_sigma(values: List[float]) -> float:
    median = statistics.median(values)
    return max(SIGMA_FLOOR_DEG, 1.4826 * statistics.median(abs(v - median) for v in values))


def _baseline(samples: List[_Sample], windows: PhaseWindows) -> Optional[_Baseline]:
    read = windows.phase("read")
    inside = [s for s in samples if read.start + BASELINE_SKIP_START_SECONDS <= s.t <= read.end - BASELINE_SKIP_END_SECONDS]
    if len(inside) < MIN_BASELINE_FRAMES:
        return None
    yaws, pitches = [s.yaw for s in inside], [s.pitch for s in inside]
    return _Baseline(statistics.median(yaws), statistics.median(pitches), _robust_sigma(yaws), _robust_sigma(pitches))


def _displacements(samples: List[_Sample], axis: _Axis, base: _Baseline, start: float, end: float) -> List[Tuple[float, float]]:
    """(time, displacement toward the asked direction) for the samples inside [start, end]."""
    origin = base.yaw if axis.key == "yaw" else base.pitch
    return [(s.t, axis.sign * ((s.yaw if axis.key == "yaw" else s.pitch) - origin)) for s in samples if start <= s.t <= end]


def _longest_run(points: List[Tuple[float, float]], holds) -> Tuple[float, float]:
    """
    Longest stretch of consecutive samples for which `holds(displacement)` is true, bridging gaps of
    at most MAX_GAP_SECONDS (a lost face). Returns (duration, end time); (0.0, 0.0) when there is none.
    """
    best = (0.0, 0.0)
    run_start: Optional[float] = None
    previous_t = 0.0
    for t, d in points:
        if holds(d) and run_start is not None and t - previous_t <= MAX_GAP_SECONDS:
            pass  # the run continues
        elif holds(d):
            run_start = t
        else:
            run_start = None
        if run_start is not None and t - run_start >= best[0]:
            best = (t - run_start, t)
        previous_t = t
    return best


def _returned(points: List[Tuple[float, float]], after: float, tolerance: float) -> bool:
    """True when, after `after`, the displacement is back within `tolerance` for MIN_RETURN_SECONDS."""
    late = [(t, d) for t, d in points if t > after]
    duration, _ = _longest_run(late, lambda d: abs(d) <= tolerance)
    return duration >= MIN_RETURN_SECONDS


def _peak(points: List[Tuple[float, float]]) -> float:
    return max((d for _, d in points), default=0.0)


def _failure(code: str, **details: Any) -> Dict[str, Any]:
    return {"detected": False, "failure_code": code, **details}


def _baseline_problem(base: Optional[_Baseline]) -> Optional[Dict[str, Any]]:
    """The failure to report when the Read window gives no usable neutral pose, else None."""
    if base is None:
        return _failure("bad_baseline", baseline_problem="too few frames with a face in the Read window")
    if abs(base.yaw) > MAX_BASELINE_YAW_DEG or abs(base.pitch) > MAX_BASELINE_PITCH_DEG:
        return _failure(
            "bad_baseline",
            baseline_problem="not facing the camera in the Read window",
            baseline_yaw_deg=round(base.yaw, 1),
            baseline_pitch_deg=round(base.pitch, 1),
        )
    return None


def _action_context(samples: List[_Sample], axis: _Axis, windows: PhaseWindows, base: _Baseline):
    """The thresholds for this person, their displacement series in Act, and the facts to report."""
    sigma = base.sigma_yaw if axis.key == "yaw" else base.sigma_pitch
    threshold = max(axis.threshold_floor, EXCURSION_SIGMAS * sigma)
    tolerance = max(axis.return_floor, RETURN_SIGMAS * sigma)
    act_start, act_end = windows.window("act", before=WINDOW_GUARD_SECONDS, after=WINDOW_GUARD_SECONDS)
    act = _displacements(samples, axis, base, act_start, act_end)
    facts: Dict[str, Any] = {
        "threshold_deg": round(threshold, 1),
        "return_tolerance_deg": round(tolerance, 1),
        "baseline_sigma_deg": round(sigma, 2),
        # How far the person moved toward the asked direction outside Act: the empirical chance rate.
        "max_disp_read": round(_peak(_displacements(samples, axis, base, *windows.window("read"))), 1),
        "max_disp_speak": round(_peak(_displacements(samples, axis, base, *windows.window("speak"))), 1),
        "act_face_frames": len(act),
    }
    return threshold, tolerance, act, facts


def _evaluate_head_action(samples: List[_Sample], axis: _Axis, windows: PhaseWindows) -> Dict[str, Any]:
    base = _baseline(samples, windows)
    problem = _baseline_problem(base)
    if problem is not None:
        return problem

    threshold, tolerance, act, facts = _action_context(samples, axis, windows, base)
    if len(act) < MIN_ACT_FACE_FRAMES:
        return _failure("no_face", **facts)

    peak = _peak(act)
    facts["peak_displacement_deg"] = round(peak, 1)
    if peak < threshold:
        opposite = max(-d for _, d in act)
        return _failure("wrong_direction" if opposite >= threshold else "no_motion", **facts)

    hold_seconds, hold_end = _longest_run(act, lambda d: d >= threshold)
    facts["hold_seconds"] = round(hold_seconds, 2)
    if hold_seconds < MIN_HOLD_SECONDS:
        return _failure("no_hold", **facts)

    facts["returned"] = _returned(act, hold_end, tolerance)
    if not facts["returned"]:
        return _failure("no_return", **facts)
    return {"detected": True, "failure_code": None, **facts}


def phased_reason(challenge: VisualChallengeType, result: Dict[str, Any]) -> str:
    """A one-sentence, technical explanation of the outcome (friendlier wording is the frontend's job)."""
    name = challenge.value
    code = result.get("failure_code")
    if code is None and "peak_displacement_deg" in result:
        return (
            f"Challenge {name} passed: moved {result['peak_displacement_deg']} deg (needed {result['threshold_deg']}), "
            f"held {result['hold_seconds']} s and returned to within {result['return_tolerance_deg']} deg of the start."
        )
    if code is None:
        return f"Challenge {name} passed: {result.get('blink_events', 0)} blinks in the Act window."
    explanations = {
        "bad_baseline": f"the neutral pose could not be measured ({result.get('baseline_problem')})",
        "no_face": "the face was not seen for enough of the Act window",
        "no_motion": f"the head moved at most {result.get('peak_displacement_deg')} deg toward the asked direction, {result.get('threshold_deg')} needed",
        "wrong_direction": "the head moved the other way",
        "no_hold": f"the head reached {result.get('peak_displacement_deg')} deg but was held {result.get('hold_seconds')} s, {MIN_HOLD_SECONDS} s needed",
        "no_return": f"the head did not come back to within {result.get('return_tolerance_deg')} deg of the start",
    }
    return f"Challenge {name} failed ({code}): {explanations.get(code, 'not performed')}."


def _evaluate_blinks(frames: List[Dict[str, Any]], recording_start: float, windows: PhaseWindows) -> Dict[str, Any]:
    """BLINK_TWICE is no longer issued; an old session that carries it is judged on the Act window only."""
    start, end = windows.window("act", before=WINDOW_GUARD_SECONDS, after=WINDOW_GUARD_SECONDS)
    inside = [f for f in frames if f.get("time_seconds") is not None and start <= f["time_seconds"] - recording_start <= end]
    result = _blink_twice(inside)
    return {**result, "failure_code": None if result["detected"] else "no_motion"}


def evaluate_challenge_phased(
    features: Dict[str, Any],
    challenge: VisualChallengeType,
    windows: PhaseWindows,
    recording_start: float,
) -> Dict[str, Any]:
    """Judge the asked action inside the protocol windows. See the module notes for the rules."""
    frames = features.get("frames", [])
    if challenge == VisualChallengeType.BLINK_TWICE:
        return _evaluate_blinks(frames, recording_start, windows)
    return _evaluate_head_action(_timed_samples(frames, recording_start), _AXES[challenge], windows)
