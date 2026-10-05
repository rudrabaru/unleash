"""
Tests for the anti-spoofing module. The trained Xception checkpoint is not stored in git, so
the tests that need it carry the `requires_checkpoint` marker; without a checkpoint
detect_deepfake must fail honestly (never a fabricated score). detect_replay_attack is
exercised against real frames.
"""
from pathlib import Path

import pytest

from app.modules.antispoof import detect_deepfake, detect_replay_attack
from app.modules.frame_extraction import extract_frames
from _paths import GENUINE_5WORD_NOFACE_VIDEO_WEBM, require


def _frames():
    result = extract_frames(str(require(GENUINE_5WORD_NOFACE_VIDEO_WEBM)))
    assert result.frames, "no frames decoded from the video fixture"
    return result.frames


def test_deepfake_empty_frames_returns_contract_compliant_error():
    result = detect_deepfake([])
    assert result.score is None
    assert result.passed is False
    assert result.error is not None


@pytest.mark.requires_checkpoint
def test_deepfake_produces_real_scores_with_trained_checkpoint():
    """With the checkpoint present, the model produces real (not fabricated) scores."""
    frames = _frames()
    result = detect_deepfake(frames)
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
    result = detect_replay_attack([])
    assert result.score is None
    assert result.passed is False
    assert result.error is not None


def test_replay_detector_scores_real_fixture_without_crashing():
    """Real FFT/noise/brightness computation over an actual fixture, not a stub."""
    frames = _frames()
    result = detect_replay_attack(frames)
    assert result.error is None
    assert result.score is not None
    assert 0.0 <= result.score <= 1.0
    assert result.details["moire_score"] is not None
    assert result.details["noise_score"] is not None
    assert result.details["brightness_score"] is not None
    assert result.details["calibration"] == "uncalibrated"


def test_replay_detector_single_frame_does_not_crash():
    """Temporal noise needs >=2 frames; a single frame must degrade gracefully, not crash."""
    frames = _frames()[:1]
    result = detect_replay_attack(frames)
    assert result.error is None
    assert result.details["noise_score"] is None  # unmeasurable -> null, never a 0.5 placeholder
    assert result.score is not None  # combined from the sub-signals that did measure
