"""
Tests for the visual liveness + challenge compliance module (Phase 2).
Uses the real_742.webm fixture, which has no face in its video track — a
useful edge case for confirming graceful "no face detected" handling.
"""
import asyncio
from pathlib import Path

<<<<<<< HEAD
import numpy as np
=======
>>>>>>> origin/feature/deepfake-detection
import pytest

from app.modules.frame_extraction import extract_frames
from app.modules.visual import detect_visual_liveness, verify_challenge_compliance
from app.schemas.session import VisualChallengeType

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "prototypes" / "fixtures"


def _frames(name: str):
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"Fixture {name} not found")
    result = extract_frames(str(path))
    if not result.frames:
        pytest.skip(f"No frames decoded from {name}")
    return result.frames


def test_liveness_empty_frames_returns_contract_compliant_error():
    result = asyncio.run(detect_visual_liveness([]))
    assert result.score is None
    assert result.passed is False
    assert result.error is not None
    assert result.reason


def test_liveness_no_face_scores_low_not_crash():
<<<<<<< HEAD
    path = FIXTURES_DIR / "real_742.webm"
    if path.exists():
        frames = extract_frames(str(path)).frames
    else:
        frames = [np.zeros((480, 640, 3), dtype=np.uint8) for _ in range(10)]
=======
    frames = _frames("real_742.webm")
>>>>>>> origin/feature/deepfake-detection
    result = asyncio.run(detect_visual_liveness(frames))
    assert result.error is None
    assert result.score is not None
    assert 0.0 <= result.score <= 1.0
    assert result.details["face_consistency_ratio"] == 0.0


def test_challenge_compliance_no_face_fails_hard_gate():
<<<<<<< HEAD
    path = FIXTURES_DIR / "real_742.webm"
    if path.exists():
        frames = extract_frames(str(path)).frames
    else:
        frames = [np.zeros((480, 640, 3), dtype=np.uint8) for _ in range(10)]
=======
    frames = _frames("real_742.webm")
>>>>>>> origin/feature/deepfake-detection
    result = asyncio.run(verify_challenge_compliance(frames, VisualChallengeType.TURN_HEAD_LEFT.value))
    assert result.error is None
    assert result.passed is False


def test_challenge_compliance_unknown_challenge_errors_gracefully():
<<<<<<< HEAD
    result = asyncio.run(verify_challenge_compliance([], "NOT_A_REAL_CHALLENGE"))
    assert result.score is None
    assert result.passed is False
    assert result.error is not None


def test_liveness_real_face_detects_blink_and_natural_movement():
    frames = _frames("blink.mp4")
    result = asyncio.run(detect_visual_liveness(frames))
    assert result.error is None
    assert result.passed is True
    assert result.score is not None and result.score >= 0.5
    assert result.details["blink_detected"] is True
    assert result.details["natural_movement_detected"] is True
    assert result.details["ear_std"] > 0.0
    assert result.details["face_consistency_ratio"] > 0.8


def test_challenge_compliance_turn_head_left_real_video():
    frames = _frames("left.mp4")
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
    frames = _frames("right.mp4")
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
    frames = _frames("down.mp4")
    result = asyncio.run(verify_challenge_compliance(frames, VisualChallengeType.LOOK_DOWN.value))
    assert result.error is None
    assert result.passed is True


def test_lip_series_generation_real_video():
    from app.modules.visual import extract_landmark_features
    from app.modules.visual._lip_series import build_lip_series

    frames = _frames("blink.mp4")
    features = extract_landmark_features(frames)
    lip_data = build_lip_series(features, fps=30.0)

    assert lip_data["fps"] == 30.0
    assert len(lip_data["series"]) > 0
    assert "lip_openness_ratio" in lip_data["series"][0]
    assert 0.0 <= lip_data["series"][0]["lip_openness_ratio"] <= 1.0
=======
    frames = _frames("real_742.webm")
    result = asyncio.run(verify_challenge_compliance(frames, "NOT_A_REAL_CHALLENGE"))
    assert result.score is None
    assert result.passed is False
    assert result.error is not None
>>>>>>> origin/feature/deepfake-detection
