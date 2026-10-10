"""
Tests for the anti-spoofing module. The trained Xception checkpoint is not stored in git, so
the tests that need it carry the `requires_checkpoint` marker; without a checkpoint
detect_deepfake must fail honestly (never a fabricated score). detect_replay_attack is
exercised against real frames.
"""
from pathlib import Path

import pytest

from app.modules.antispoof import detect_deepfake, detect_replay_attack
from app.media.frames import load_frames
from _paths import GENUINE_5WORD_NOFACE_VIDEO_WEBM, require


def _frames():
    bundle = load_frames(require(GENUINE_5WORD_NOFACE_VIDEO_WEBM))
    assert bundle.sparse, "no frames decoded from the video fixture"
    return bundle.sparse


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


def test_a_checkpoint_loads_and_scores_frames_without_the_trained_file(tmp_path):
    """
    The load path (strict state dict, preprocessing, threshold) runs in CI, where the 250 MB trained
    checkpoint does not exist: a randomly initialised network is saved in the same format and loaded.
    The scores mean nothing; the point is that a real file of this format loads and produces valid ones.
    """
    import numpy as np
    import timm
    import torch

    from app.modules.antispoof._config import DeepfakeSettings
    from app.modules.antispoof._deepfake import XceptionDeepfakeClassifier

    torch.manual_seed(0)
    checkpoint = tmp_path / "random_xception.pth"
    torch.save({"state_dict": timm.create_model("xception", pretrained=False, num_classes=2).state_dict()}, checkpoint)
    classifier = XceptionDeepfakeClassifier(DeepfakeSettings(checkpoint_path=str(checkpoint)))
    faces = [np.random.default_rng(i).integers(0, 255, (120, 120, 3), dtype=np.uint8) for i in range(2)]

    prediction, confidence, per_frame = classifier.predict_video(faces)

    assert prediction in ("REAL", "FAKE") and 0.0 <= confidence <= 1.0
    assert len(per_frame) == 2 and all(0.0 <= p <= 1.0 for p in per_frame)


def test_an_incompatible_checkpoint_is_reported_not_loaded(tmp_path):
    import numpy as np
    import torch

    from app.modules.antispoof._config import DeepfakeSettings
    from app.modules.antispoof._deepfake import ModelNotReadyError, XceptionDeepfakeClassifier

    checkpoint = tmp_path / "wrong_shape.pth"
    torch.save({"state_dict": {"fc.weight": torch.zeros(3, 3)}}, checkpoint)
    classifier = XceptionDeepfakeClassifier(DeepfakeSettings(checkpoint_path=str(checkpoint)))

    with pytest.raises(ModelNotReadyError, match="not compatible"):
        classifier.predict_video([np.zeros((64, 64, 3), dtype=np.uint8)])
