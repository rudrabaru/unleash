"""
The phase-aware head-action check (app/modules/visual/_pose_phased.py) on synthetic head-pose
series, one rule at a time, then through verify_challenge_compliance.

Series are sampled at about 9 frames a second over 13 s, like the dense frames of a real
recording. Yaw is positive toward the person's own left in an unmirrored feed (see _pose.py).
"""
import math

import pytest

from app.modules.visual import verify_challenge_compliance
from app.modules.visual._pose_phased import evaluate_challenge_phased
from app.protocol import PROTOCOL_V1
from app.schemas.session import VisualChallengeType as C

STEP = 0.11  # seconds between frames


def _series(yaw=lambda t: 0.0, pitch=lambda t: 0.0, offset=0.0, face=lambda t: True, seconds=13.2):
    """Feature frames as the landmark step produces them; `offset` shifts the clock like a late recorder start."""
    frames = []
    for i in range(int(seconds / STEP)):
        t = i * STEP
        present = face(t)
        frames.append({
            "time_seconds": t + offset,
            "yaw": yaw(t) if present else None,
            "pitch": pitch(t) if present else None,
            "ear": 0.3 if present else None,
            "face_present": present,
        })
    return {"frames": frames}


def _turn(peak, start=8.5, hold_until=10.5, back_by=11.2):
    """0 until `start`, ramps to `peak`, stays until `hold_until`, ramps back to 0 by `back_by`."""
    def f(t):
        if t < start:
            return 0.0
        if t < start + 0.4:
            return peak * (t - start) / 0.4
        if t < hold_until:
            return peak
        if t < back_by:
            return peak * (1 - (t - hold_until) / (back_by - hold_until))
        return 0.0
    return f


def _check(features, challenge=C.TURN_HEAD_LEFT, recording_start=0.0):
    return evaluate_challenge_phased(features, challenge, PROTOCOL_V1, recording_start)


# --- the action: turn, hold, return, in the Act window ------------------------------------------

def test_a_turn_held_and_returned_to_centre_in_act_passes():
    result = _check(_series(yaw=_turn(30.0)))

    assert result["detected"] is True and result["failure_code"] is None
    assert result["peak_displacement_deg"] == pytest.approx(30.0, abs=0.5)
    assert result["hold_seconds"] >= 0.4 and result["returned"] is True


@pytest.mark.parametrize("challenge, yaw_sign, pitch_sign", [
    (C.TURN_HEAD_LEFT, +1, 0), (C.TURN_HEAD_RIGHT, -1, 0), (C.LOOK_DOWN, 0, +1), (C.LOOK_UP, 0, -1),
])
def test_each_direction_needs_its_own_sign(challenge, yaw_sign, pitch_sign):
    shape = _turn(30.0)
    right_way = _series(yaw=lambda t: yaw_sign * shape(t), pitch=lambda t: pitch_sign * shape(t))
    other_way = _series(yaw=lambda t: -yaw_sign * shape(t), pitch=lambda t: -pitch_sign * shape(t))

    assert _check(right_way, challenge)["detected"] is True
    result = _check(other_way, challenge)
    assert result["detected"] is False and result["failure_code"] == "wrong_direction"


def test_a_peak_that_is_not_held_is_no_hold():
    result = _check(_series(yaw=_turn(30.0, start=8.5, hold_until=8.7, back_by=9.2)))

    assert result["failure_code"] == "no_hold" and result["hold_seconds"] < 0.4


def test_a_turn_that_never_comes_back_is_no_return():
    result = _check(_series(yaw=_turn(30.0, back_by=99.0, hold_until=99.0)))

    assert result["failure_code"] == "no_return" and result["returned"] is False


def test_small_movements_are_no_motion():
    result = _check(_series(yaw=lambda t: 5.0 if 9 < t < 10 else 0.0))

    assert result["failure_code"] == "no_motion"


# --- only the Act window counts ----------------------------------------------------------------

def test_a_turn_during_speak_does_not_count_and_is_logged():
    result = _check(_series(yaw=_turn(30.0, start=4.0, hold_until=6.0, back_by=6.8)))

    assert result["failure_code"] == "no_motion"
    assert result["max_disp_speak"] >= 25.0 and result["max_disp_read"] < 5.0


def test_a_nod_while_speaking_does_not_pass_look_up():
    result = _check(_series(pitch=lambda t: -15.0 if 4 < t < 5 else 0.0), C.LOOK_UP)

    assert result["detected"] is False and result["failure_code"] == "no_motion"


def test_a_late_recorder_start_is_handled_by_the_recording_start():
    features = _series(yaw=_turn(30.0), offset=0.5)

    assert _check(features, recording_start=0.5)["detected"] is True


# --- what makes a baseline ---------------------------------------------------------------------

def test_a_jittery_baseline_raises_the_bar():
    jitter = lambda t: 9.0 * math.sin(20.0 * t) if t < 3 else 0.0  # a restless head while the baseline is taken
    steady = _check(_series(yaw=_turn(25.0)))
    shaky = _check(_series(yaw=lambda t: jitter(t) + _turn(25.0)(t)))

    assert steady["detected"] is True
    assert shaky["detected"] is False and shaky["threshold_deg"] > 25.0


def test_no_face_in_read_is_a_bad_baseline_not_a_missed_action():
    result = _check(_series(yaw=_turn(30.0), face=lambda t: t > 3.0))

    assert result["failure_code"] == "bad_baseline"


def test_not_facing_the_camera_in_read_is_a_bad_baseline():
    result = _check(_series(yaw=lambda t: 35.0))

    assert result["failure_code"] == "bad_baseline"


def test_no_face_in_act_is_reported_as_no_face():
    result = _check(_series(yaw=_turn(30.0), face=lambda t: t < 8.0))

    assert result["failure_code"] == "no_face"


def test_a_face_lost_for_a_moment_does_not_break_the_hold():
    blink_out = lambda t: not (9.4 < t < 9.6)

    assert _check(_series(yaw=_turn(30.0), face=blink_out))["detected"] is True


# --- through the detector contract -------------------------------------------------------------

def test_the_detector_result_reports_the_code_and_a_readable_reason():
    result = verify_challenge_compliance(
        ["frame"], C.TURN_HEAD_LEFT.value, features=_series(yaw=_turn(30.0, back_by=99.0, hold_until=99.0)),
        phases=PROTOCOL_V1, recording_start=0.0,
    )

    assert result.passed is False and result.error is None and result.score is not None
    assert result.details["failure_code"] == "no_return" and result.details["phase_aware"] is True
    assert "no_return" in result.reason and "TURN_HEAD_LEFT" in result.reason


def test_a_pass_scores_one_and_says_what_was_done():
    result = verify_challenge_compliance(
        ["frame"], C.TURN_HEAD_LEFT.value, features=_series(yaw=_turn(30.0)), phases=PROTOCOL_V1, recording_start=0.0,
    )

    assert result.passed is True and result.score == 1.0
    assert "held" in result.reason and "returned" in result.reason


def test_a_check_that_could_not_judge_has_no_score():
    result = verify_challenge_compliance(
        ["frame"], C.TURN_HEAD_LEFT.value, features=_series(yaw=_turn(30.0), face=lambda t: t > 3.0),
        phases=PROTOCOL_V1, recording_start=0.0,
    )

    assert result.passed is False and result.score is None and result.error is None
    assert result.details["failure_code"] == "bad_baseline"


def test_without_windows_the_old_whole_recording_check_still_applies():
    result = verify_challenge_compliance(["frame"], C.TURN_HEAD_LEFT.value, features=_series(yaw=_turn(30.0, start=4.0)))

    assert result.details["phase_aware"] is False  # a turn in Speak passes when no windows are given
    assert result.passed is True


def test_blink_twice_from_an_old_session_is_judged_in_act_only():
    def blinks(t):  # two blinks in Read, none in Act
        return 0.1 if int(t * 2) in (1, 3) and t < 3 else 0.3

    features = _series()
    for frame in features["frames"]:
        frame["ear"] = blinks(frame["time_seconds"])

    result = _check(features, C.BLINK_TWICE)

    assert result["detected"] is False and result["failure_code"] == "no_motion"
