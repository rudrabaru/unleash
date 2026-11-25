"""
The phase-aware head action on a real face: MediaPipe, the recording clock and the Act window working
together. The clips are built from the real TURN_LEFT sample (see `phased_turn_clip` in conftest).
"""
from app import orchestrator
from app.media.frames import DENSE_MAX_EDGE, load_frames
from app.media.probe import probe_streams
from app.modules.visual import extract_landmark_features, verify_challenge_compliance
from app.protocol import PROTOCOL_V1
from _paths import GENUINE_5WORD_PHRASE


def _challenge_result(clip, challenge):
    bundle = load_frames(clip, dense_max_edge=DENSE_MAX_EDGE)
    features = extract_landmark_features(bundle.dense, timestamps=bundle.dense_times, original_indices=bundle.dense_indices)
    return verify_challenge_compliance(
        bundle.dense, challenge, features=features, phases=PROTOCOL_V1,
        recording_start=probe_streams(clip).recording_start,
    )


def test_a_real_left_turn_held_and_returned_in_act_passes_left(phased_turn_clip):
    result = _challenge_result(phased_turn_clip(8.0), "TURN_HEAD_LEFT")

    assert result.passed is True, result.reason
    assert result.details["hold_seconds"] >= 0.4 and result.details["returned"] is True
    assert result.details["max_disp_read"] < 5.0 and result.details["max_disp_speak"] < 5.0


def test_the_same_recording_fails_a_right_turn_challenge_as_the_wrong_direction(phased_turn_clip):
    result = _challenge_result(phased_turn_clip(8.0), "TURN_HEAD_RIGHT")

    assert result.passed is False
    assert result.details["failure_code"] == "wrong_direction"


def test_a_real_turn_made_during_speak_instead_of_act_is_not_accepted(phased_turn_clip):
    # The turn starts as the baseline ends and is over before Act begins (7.6 s with the guard).
    result = _challenge_result(phased_turn_clip(2.7), "TURN_HEAD_LEFT")

    assert result.passed is False
    assert result.details["failure_code"] == "no_motion"
    assert result.details["max_disp_speak"] > 25.0  # the turn happened, just at the wrong time


def test_the_whole_analysis_hands_the_windows_to_the_challenge(phased_turn_clip):
    analysis = orchestrator.analyze_media(
        phased_turn_clip(8.0), "TURN_HEAD_LEFT", GENUINE_5WORD_PHRASE, phases=PROTOCOL_V1
    )

    challenge = analysis.signals["visual_challenge"]
    assert challenge.passed is True, challenge.reason
    assert challenge.details["phase_aware"] is True
    assert "probe" in analysis.timings and analysis.phases is PROTOCOL_V1
