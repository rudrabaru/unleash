"""
Deepfake detector configuration. Owns the constants that used to live in
training/train_xception.py so the runtime module never has to import the
training script.
"""
from dataclasses import dataclass
from pathlib import Path
import os

# Anchored to the backend folder, not the process working directory, so the default
# checkpoint is found whether the server starts from backend/ or from the repo root.
_DEFAULT_CHECKPOINT = str(Path(__file__).resolve().parents[3] / "checkpoints" / "xception_deepfake_best.pth")

FAKE_CLASS_INDEX = 1
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def _get_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        return default


@dataclass(frozen=True)
class DeepfakeSettings:
    model_name: str = os.getenv("UNLEASH_XCEPTION_MODEL_NAME", "xception")
    checkpoint_path: str | None = os.getenv("UNLEASH_XCEPTION_CHECKPOINT", _DEFAULT_CHECKPOINT)
    fake_threshold: float = _get_float("UNLEASH_FAKE_THRESHOLD", 0.5)
    image_size: int = _get_int("UNLEASH_IMAGE_SIZE", 299)
    fake_class_index: int = _get_int("UNLEASH_FAKE_CLASS_INDEX", FAKE_CLASS_INDEX)


settings = DeepfakeSettings()
