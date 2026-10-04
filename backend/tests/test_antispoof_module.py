"""
Tests for the anti-spoofing module. No trained Xception checkpoint ships with this
repo (Phase 3), so detect_deepfake must fail honestly (J5: never a fabricated score)
rather than crash or invent a plausible-looking result. detect_replay_attack (Phase 4)
is real and is exercised against actual fixture frames.
"""
import asyncio
from pathlib import Path

import pytest

from app.modules.antispoof import detect_deepfake, detect_replay_attack
from app.modules.frame_extraction import extract_frames

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "prototypes" / "fixtures"


def _frames(name: str):
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"Fixture {name} not found")
    result = extract_frames(str(path))
    if not result.frames:
        pytest.skip(f"No frames decoded from {name}")
    return result.frames


def test_deepfake_empty_frames_returns_contract_compliant_error():
    result = asyncio.run(detect_deepfake([]))
    assert result.score is None
    assert result.passed is False
    assert result.error is not None


def test_deepfake_produces_real_scores_with_trained_checkpoint():
    """Phase 3 complete: checkpoint exists, model produces real (not fabricated) scores."""
    frames = _frames("real_742.webm")
    result = asyncio.run(detect_deepfake(frames))
    assert result.error is None
    assert result.score is not None
    assert 0.0 <= result.score <= 1.0
    assert result.details["prediction"] in ("REAL", "FAKE")
    assert result.details["processed_frames"] > 0


def test_default_checkpoint_path_does_not_depend_on_working_directory():
    """Regression: a cwd-relative default made the deepfake signal vanish when started from the repo root."""
    from app.modules.antispoof._config import DeepfakeSettings

    default = Path(DeepfakeSettings.checkpoint_path)
    assert default.is_absolute()
    assert default.parent.name == "checkpoints"
    assert default.parent.parent.name == "backend"


def test_replay_empty_frames_returns_contract_compliant_error():
    result = asyncio.run(detect_replay_attack([]))
    assert result.score is None
    assert result.passed is False
    assert result.error is not None


def test_replay_detector_scores_real_fixture_without_crashing():
    """Phase 4: real FFT/noise/brightness computation over an actual fixture, not a stub."""
    frames = _frames("real_742.webm")
    result = asyncio.run(detect_replay_attack(frames))
    assert result.error is None
    assert result.score is not None
    assert 0.0 <= result.score <= 1.0
    assert result.details["moire_score"] is not None
    assert result.details["noise_score"] is not None
    assert result.details["brightness_score"] is not None
    assert result.details["calibration"] == "uncalibrated"


def test_replay_detector_single_frame_does_not_crash():
    """Temporal noise needs >=2 frames; a single frame must degrade gracefully, not crash."""
    frames = _frames("real_742.webm")[:1]
    result = asyncio.run(detect_replay_attack(frames))
    assert result.error is None
    assert result.details["noise_score"] is None  # unmeasurable -> null, never a 0.5 placeholder
    assert result.score is not None  # combined from the sub-signals that did measure
