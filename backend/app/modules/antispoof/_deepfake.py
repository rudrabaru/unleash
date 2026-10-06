"""
Deepfake Detector: a self-trained Xception classifier, forced to CPU (the project is CPU-only).

The trained checkpoint (~250 MB) is not stored in git (`*.pth` is ignored) and is not yet
published; it is read from UNLEASH_XCEPTION_CHECKPOINT or, by default, from
backend/checkpoints/xception_deepfake_best.pth. Without a real file this module returns an
honest error result, never a fabricated score.

The classifier expects face crops (see `app/media/face_crop.py`, built from the MediaPipe
landmarks); the caller crops, this module only resizes and scores what it is given.
"""
from pathlib import Path
from typing import List

import cv2
import numpy as np
import timm
import torch

from app.media.sampling import sample_indices
from app.modules.antispoof._config import IMAGENET_MEAN, IMAGENET_STD, DeepfakeSettings, settings

# Frames scored per video. Xception costs about 0.3 s per frame on CPU, so this bounds the
# time spent here; the average over frames is what the verdict uses.
MAX_SCORED_FRAMES = 12


class ModelNotReadyError(Exception):
    """Raised when a trained Xception checkpoint has not been configured."""


class XceptionDeepfakeClassifier:
    def __init__(self, config: DeepfakeSettings) -> None:
        self.settings = config
        self.device = torch.device("cpu")
        self.model = None

    def predict_video(self, frames: List[np.ndarray]) -> tuple:
        if not frames:
            raise ValueError("At least one frame is required for prediction.")

        sampled_frames = [frames[i] for i in sample_indices(len(frames), MAX_SCORED_FRAMES)]

        model = self._load_model()
        fake_probabilities = [self._predict_frame(model, frame) for frame in sampled_frames]
        video_fake_probability = float(np.mean(fake_probabilities))

        if video_fake_probability >= self.settings.fake_threshold:
            return "FAKE", video_fake_probability, fake_probabilities

        real_confidence = 1.0 - video_fake_probability
        return "REAL", real_confidence, fake_probabilities

    def _load_model(self):
        if self.model is not None:
            return self.model

        if not self.settings.checkpoint_path:
            raise ModelNotReadyError(
                "UNLEASH_XCEPTION_CHECKPOINT is not set. Provide a trained Xception checkpoint before inference."
            )

        checkpoint_path = Path(self.settings.checkpoint_path)
        if not checkpoint_path.exists():
            raise ModelNotReadyError(f"model not loaded: checkpoint missing ({checkpoint_path})")

        model = timm.create_model(self.settings.model_name, pretrained=False, num_classes=2)
        checkpoint = torch.load(checkpoint_path, map_location=self.device, weights_only=True)
        state_dict = _extract_state_dict(checkpoint)
        try:
            model.load_state_dict(_strip_module_prefix(state_dict), strict=True)
        except RuntimeError as exc:
            raise ModelNotReadyError("Configured checkpoint is not compatible with the Xception model.") from exc
        model.to(self.device)
        model.eval()

        self.model = model
        return model

    def _predict_frame(self, model, frame: np.ndarray) -> float:
        tensor = self._preprocess_frame(frame)

        with torch.no_grad():
            logits = model(tensor)

        probabilities = torch.softmax(logits.squeeze(0), dim=0)
        return float(probabilities[self.settings.fake_class_index].item())

    def _preprocess_frame(self, frame: np.ndarray):
        # frame is already RGB (from the shared frame loader)
        resized_frame = cv2.resize(
            frame,
            (self.settings.image_size, self.settings.image_size),
            interpolation=cv2.INTER_AREA,
        )
        normalized_frame = resized_frame.astype(np.float32) / 255.0
        normalized_frame = (normalized_frame - np.array(IMAGENET_MEAN, dtype=np.float32)) / np.array(
            IMAGENET_STD, dtype=np.float32
        )
        tensor = torch.from_numpy(normalized_frame).permute(2, 0, 1).unsqueeze(0).float()
        return tensor.to(self.device)


def _extract_state_dict(checkpoint) -> dict:
    if not isinstance(checkpoint, dict):
        raise ModelNotReadyError("Checkpoint must be a PyTorch state dictionary.")
    for key in ("state_dict", "model_state_dict", "model"):
        value = checkpoint.get(key)
        if isinstance(value, dict):
            return value
    return checkpoint


def _strip_module_prefix(state_dict: dict) -> dict:
    return {key.removeprefix("module."): value for key, value in state_dict.items()}


classifier = XceptionDeepfakeClassifier(settings)
