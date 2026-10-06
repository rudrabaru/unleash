"""
Deepfake detector configuration. Owns the constants that used to live in
training/train_xception.py so the runtime module never has to import the
training script.
"""
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings as app_settings

# Anchored to the backend folder, not the process working directory, so the default
# checkpoint is found whether the server starts from backend/ or from the repo root.
_DEFAULT_CHECKPOINT = str(Path(__file__).resolve().parents[3] / "checkpoints" / "xception_deepfake_best.pth")

FAKE_CLASS_INDEX = app_settings.FAKE_CLASS_INDEX
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


@dataclass(frozen=True)
class DeepfakeSettings:
    model_name: str = app_settings.XCEPTION_MODEL_NAME
    checkpoint_path: str | None = app_settings.XCEPTION_CHECKPOINT or _DEFAULT_CHECKPOINT
    fake_threshold: float = app_settings.FAKE_THRESHOLD
    image_size: int = app_settings.IMAGE_SIZE
    fake_class_index: int = app_settings.FAKE_CLASS_INDEX


settings = DeepfakeSettings()
