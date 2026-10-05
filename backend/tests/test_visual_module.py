"""
Tests for the visual liveness and challenge-compliance module.
`genuine_5word_noface_video.webm` has no face in its video track, which is the edge case for
confirming graceful "no face detected" handling; the real-face clips cover the head turns,
looking up/down and blinking.
"""
import asyncio
from pathlib import Path

import pytest

from app.modules.visual import (
    detect_visual_liveness,
    extract_visual_frames,
    verify_challenge_compliance,
)
from app.schemas.session import VisualChallengeType

from _paths import GENUINE_5WORD_NOFACE_VIDEO_WEBM, require

# real-face clips (they move to tests/fixtures/video in the fixture reorganisation)
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "prototypes" / "fixtures"


def _frames(name: str):
    path = require(FIXTURES_DIR / name)
    result = extract_visual_frames(str(path))
    assert result.frames, f"no frames decoded from {name}"
    return result.frames


def test_liveness_empty_frames_returns_contract_compliant_error():
    result = asyncio.run(detect_visual_liveness([]))
    assert result.score is None
    assert result.passed is False
    assert result.error is not None
    assert result.reason


def test_liveness_no_face_scores_low_not_crash():
    frames = extract_visual_frames(str(require(GENUINE_5WORD_NOFACE_VIDEO_WEBM))).frames
    assert frames
    result = asyncio.run(detect_visual_liveness(frames))
    assert result.error is None
    assert result.score is not None
    assert 0.0 <= result.score <= 1.0
    assert result.details["face_consistency_ratio"] == 0.0


def test_challenge_compliance_no_face_fails_the_must_pass_check():
    frames = extract_visual_frames(str(require(GENUINE_5WORD_NOFACE_VIDEO_WEBM))).frames
    assert frames
    result = asyncio.run(verify_challenge_compliance(frames, VisualChallengeType.TURN_HEAD_LEFT.value))
    assert result.error is None
    assert result.passed is False


def test_challenge_compliance_unknown_challenge_errors_gracefully():
    result = asyncio.run(verify_challenge_compliance([], "NOT_A_REAL_CHALLENGE"))
    assert result.score is None
    assert result.passed is False
    assert result.error is not None


def test_liveness_real_face_detects_blink_and_natural_movement():
    frames = _frames("BLINKING.webm")
    result = asyncio.run(detect_visual_liveness(frames))
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
    result_left = asyncio.run(verify_challenge_compliance(frames, VisualChallengeType.TURN_HEAD_LEFT.value))
    assert result_left.error is None
    assert result_left.passed is True
    assert result_left.score == 1.0

    # Opposite challenge must fail
    result_right = asyncio.run(verify_challenge_compliance(frames, VisualChallengeType.TURN_HEAD_RIGHT.value))
    assert result_right.error is None
    assert result_right.passed is False


def test_challenge_compliance_turn_head_right_real_video():
    frames = _frames("TURN_RIGHT.webm")
    # Correct challenge must pass
    result_right = asyncio.run(verify_challenge_compliance(frames, VisualChallengeType.TURN_HEAD_RIGHT.value))
    assert result_right.error is None
    assert result_right.passed is True
    assert result_right.score == 1.0

    # Opposite challenge must fail
    result_left = asyncio.run(verify_challenge_compliance(frames, VisualChallengeType.TURN_HEAD_LEFT.value))
    assert result_left.error is None
    assert result_left.passed is False


def test_challenge_compliance_look_down_real_video():
    frames = _frames("DOWN.webm")
    result = asyncio.run(verify_challenge_compliance(frames, VisualChallengeType.LOOK_DOWN.value))
    assert result.error is None
    assert result.passed is True


def test_challenge_compliance_look_up_real_video():
    frames = _frames("UP.webm")
    result = asyncio.run(verify_challenge_compliance(frames, VisualChallengeType.LOOK_UP.value))
    assert result.error is None
    assert result.passed is True


def test_look_down_does_not_pass_blink_twice():
    frames = _frames("DOWN.webm")
    result = asyncio.run(verify_challenge_compliance(frames, VisualChallengeType.BLINK_TWICE.value))
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
