"""
Tests for the visual liveness + challenge compliance module (Phase 2).
Uses the real_742.webm fixture, which has no face in its video track — a
useful edge case for confirming graceful "no face detected" handling.
"""
import asyncio
from pathlib import Path

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
    frames = _frames("real_742.webm")
    result = asyncio.run(detect_visual_liveness(frames))
    assert result.error is None
    assert result.score is not None
    assert 0.0 <= result.score <= 1.0
    assert result.details["face_consistency_ratio"] == 0.0


def test_challenge_compliance_no_face_fails_hard_gate():
    frames = _frames("real_742.webm")
    result = asyncio.run(verify_challenge_compliance(frames, VisualChallengeType.TURN_HEAD_LEFT.value))
    assert result.error is None
    assert result.passed is False


def test_challenge_compliance_unknown_challenge_errors_gracefully():
    frames = _frames("real_742.webm")
    result = asyncio.run(verify_challenge_compliance(frames, "NOT_A_REAL_CHALLENGE"))
    assert result.score is None
    assert result.passed is False
    assert result.error is not None
