from dataclasses import dataclass
import os

from training.train_xception import FAKE_CLASS_INDEX


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
class Settings:
    model_name: str = os.getenv("UNLEASH_XCEPTION_MODEL_NAME", "xception")
    checkpoint_path: str | None = os.getenv("UNLEASH_XCEPTION_CHECKPOINT", "checkpoints/xception_deepfake_best.pth")
    fake_threshold: float = _get_float("UNLEASH_FAKE_THRESHOLD", 0.5)
    max_sampled_frames: int = _get_int("UNLEASH_MAX_FRAMES", 16)
    image_size: int = _get_int("UNLEASH_IMAGE_SIZE", 299)
    enable_face_crop: bool = _get_bool("UNLEASH_ENABLE_FACE_CROP", True)
    fake_class_index: int = _get_int("UNLEASH_FAKE_CLASS_INDEX", FAKE_CLASS_INDEX)


settings = Settings()
