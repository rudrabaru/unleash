"""
Deepfake detector configuration. Owns the constants that used to live in
training/train_xception.py so the runtime module never has to import the
training script (see Phase 3: invert the config -> training import direction).
"""
from dataclasses import dataclass
import os

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


def _get_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class DeepfakeSettings:
    model_name: str = os.getenv("UNLEASH_XCEPTION_MODEL_NAME", "xception")
    checkpoint_path: str | None = os.getenv("UNLEASH_XCEPTION_CHECKPOINT", "checkpoints/xception_deepfake_best.pth")
    fake_threshold: float = _get_float("UNLEASH_FAKE_THRESHOLD", 0.5)
    image_size: int = _get_int("UNLEASH_IMAGE_SIZE", 299)
    enable_face_crop: bool = _get_bool("UNLEASH_ENABLE_FACE_CROP", True)
    fake_class_index: int = _get_int("UNLEASH_FAKE_CLASS_INDEX", FAKE_CLASS_INDEX)


settings = DeepfakeSettings()
