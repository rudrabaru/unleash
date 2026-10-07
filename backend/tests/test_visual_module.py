"""
Tests for the visual liveness and challenge-compliance module.
`genuine_5word_noface_video.webm` has no face in its video track, which is the edge case for
confirming graceful "no face detected" handling; the real-face clips cover the head turns,
looking up/down and blinking.
"""


from app.media.frames import DENSE_MAX_EDGE, load_frames
from app.modules.visual import detect_visual_liveness, verify_challenge_compliance
from app.schemas.session import VisualChallengeType

from _paths import GENUINE_5WORD_NOFACE_VIDEO_WEBM, VIDEO_FIXTURES_DIR, require


def _frames(name: str):
    path = require(VIDEO_FIXTURES_DIR / name)
    bundle = load_frames(path, dense_max_edge=DENSE_MAX_EDGE)  # the same frames the pipeline gives the detectors
    assert bundle.dense, f"no frames decoded from {name}"
    return bundle.dense


def test_liveness_empty_frames_returns_contract_compliant_error():
    result = detect_visual_liveness([])
    assert result.score is None
    assert result.passed is False
    assert result.error is not None
    assert result.reason


def test_liveness_no_face_scores_low_not_crash():
    frames = load_frames(require(GENUINE_5WORD_NOFACE_VIDEO_WEBM), dense_max_edge=DENSE_MAX_EDGE).dense
    assert frames
    result = detect_visual_liveness(frames)
    assert result.error is None
    assert result.score is not None
    assert 0.0 <= result.score <= 1.0
    assert result.details["face_consistency_ratio"] == 0.0


def test_challenge_compliance_no_face_fails_the_must_pass_check():
    frames = load_frames(require(GENUINE_5WORD_NOFACE_VIDEO_WEBM), dense_max_edge=DENSE_MAX_EDGE).dense
    assert frames
    result = verify_challenge_compliance(frames, VisualChallengeType.TURN_HEAD_LEFT.value)
    assert result.error is None
    assert result.passed is False


def test_challenge_compliance_unknown_challenge_errors_gracefully():
    result = verify_challenge_compliance([], "NOT_A_REAL_CHALLENGE")
    assert result.score is None
    assert result.passed is False
    assert result.error is not None


def test_liveness_real_face_detects_blink_and_natural_movement():
    frames = _frames("BLINKING.webm")
    result = detect_visual_liveness(frames)
    assert result.error is None
    assert result.passed is True
    assert result.score is not None and result.score >= 0.5
    assert result.details["blink_detected"] is True
    assert result.details["natural_movement_detected"] is True
    assert result.details["ear_std"] > 0.0
    assert result.details["face_consistency_ratio"] > 0.8


def test_challenge_compliance_turn_head_left_real_video():
    frames = _frames("TURN_LEFT.webm")
    # Correct challenge must pass
    result_left = verify_challenge_compliance(frames, VisualChallengeType.TURN_HEAD_LEFT.value)
    assert result_left.error is None
    assert result_left.passed is True
    assert result_left.score == 1.0

    # Opposite challenge must fail
    result_right = verify_challenge_compliance(frames, VisualChallengeType.TURN_HEAD_RIGHT.value)
    assert result_right.error is None
    assert result_right.passed is False


def test_challenge_compliance_turn_head_right_real_video():
    frames = _frames("TURN_RIGHT.webm")
    # Correct challenge must pass
    result_right = verify_challenge_compliance(frames, VisualChallengeType.TURN_HEAD_RIGHT.value)
    assert result_right.error is None
    assert result_right.passed is True
    assert result_right.score == 1.0

    # Opposite challenge must fail
    result_left = verify_challenge_compliance(frames, VisualChallengeType.TURN_HEAD_LEFT.value)
    assert result_left.error is None
    assert result_left.passed is False


def test_challenge_compliance_look_down_real_video():
    frames = _frames("DOWN.webm")
    result = verify_challenge_compliance(frames, VisualChallengeType.LOOK_DOWN.value)
    assert result.error is None
    assert result.passed is True


def test_challenge_compliance_look_up_real_video():
    frames = _frames("UP.webm")
    result = verify_challenge_compliance(frames, VisualChallengeType.LOOK_UP.value)
    assert result.error is None
    assert result.passed is True


def test_look_down_does_not_pass_blink_twice():
    frames = _frames("DOWN.webm")
    result = verify_challenge_compliance(frames, VisualChallengeType.BLINK_TWICE.value)
    assert result.error is None
    assert result.passed is False, "Looking down should not trigger blink-twice challenge"


def test_lip_series_generation_real_video():
    from app.modules.visual import extract_landmark_features
    from app.modules.visual._lip_series import build_lip_series

    frames = _frames("BLINKING.webm")
    features = extract_landmark_features(frames)
    lip_data = build_lip_series(features, fps=30.0)

    assert lip_data["fps"] == 30.0
    assert len(lip_data["series"]) > 0
    assert "lip_openness_ratio" in lip_data["series"][0]
    assert 0.0 <= lip_data["series"][0]["lip_openness_ratio"] <= 1.0


def test_blink_twice_ignores_initial_closed_eyes_without_prior_open():
    """Verify that a recording starting with closed eyes does not count them as a blink (BUG-5)."""
    from app.modules.visual._pose import _blink_twice

    # 1. Closed from the very start to the end (no prior open frame) -> 0 blinks
    closed_all = [{"ear": 0.12, "pitch": 0.0, "yaw": 0.0} for _ in range(30)]
    assert _blink_twice(closed_all)["blink_events"] == 0

    # 2. Open first, then 2 distinct closed dips -> 2 blinks
    two_blinks = (
        [{"ear": 0.30, "pitch": 0.0, "yaw": 0.0} for _ in range(5)] +
        [{"ear": 0.12, "pitch": 0.0, "yaw": 0.0} for _ in range(4)] +
        [{"ear": 0.30, "pitch": 0.0, "yaw": 0.0} for _ in range(5)] +
        [{"ear": 0.12, "pitch": 0.0, "yaw": 0.0} for _ in range(4)] +
        [{"ear": 0.30, "pitch": 0.0, "yaw": 0.0} for _ in range(5)]
    )
    assert _blink_twice(two_blinks)["blink_events"] == 2

