"""
Deepfake Detector: self-trained Xception classifier (kept per team decision —
see implement-all-three-pillars Phase 3), forced to CPU unconditionally per
CLAUDE.md Section G's GPU ban. Ported from deepfake_detection/app/model.py.

No trained checkpoint ships with this repo. Until UNLEASH_XCEPTION_CHECKPOINT
points at a real file, this module returns an honest error result — never a
fabricated score (J5).
"""
from pathlib import Path
from typing import List

import numpy as np

from app.modules.antispoof._config import IMAGENET_MEAN, IMAGENET_STD, DeepfakeSettings, settings
from app.modules.antispoof._face_crop import crop_primary_face

try:
    import cv2
    import torch
    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    TORCH_AVAILABLE = False


class ModelNotReadyError(Exception):
    """Raised when a trained Xception checkpoint has not been configured."""


class XceptionDeepfakeClassifier:
    def __init__(self, config: DeepfakeSettings) -> None:
        self.settings = config
        self.device = torch.device("cpu") if TORCH_AVAILABLE else None
        self.model = None

    def predict_video(self, frames: List[np.ndarray]) -> tuple:
        if not frames:
            raise ValueError("At least one frame is required for prediction.")

        # Sample frames to reduce inference latency: use every Nth frame if too many
        # Keeps at most 20 frames for analysis; averaging across sampled frames is sufficient
        max_frames = 20
        sampled_frames = frames if len(frames) <= max_frames else [frames[i] for i in range(0, len(frames), len(frames) // max_frames)]

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

        if not TORCH_AVAILABLE:
            raise ModelNotReadyError("torch is not installed.")

        if not self.settings.checkpoint_path:
            raise ModelNotReadyError(
                "UNLEASH_XCEPTION_CHECKPOINT is not set. Provide a trained Xception checkpoint before inference."
            )

        checkpoint_path = Path(self.settings.checkpoint_path)
        if not checkpoint_path.exists():
            raise ModelNotReadyError(f"model not loaded: checkpoint missing ({checkpoint_path})")

        try:
            import timm
        except ImportError as exc:
            raise ModelNotReadyError("The timm package is required to create the Xception model.") from exc

        model = timm.create_model(self.settings.model_name, pretrained=False, num_classes=2)
        checkpoint = torch.load(checkpoint_path, map_location=self.device)
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
        processed_frame = crop_primary_face(frame) if self.settings.enable_face_crop else frame
        tensor = self._preprocess_frame(processed_frame)

        with torch.no_grad():
            logits = model(tensor)

        if logits.shape[-1] == 1:
            return float(torch.sigmoid(logits.squeeze()).item())

        probabilities = torch.softmax(logits.squeeze(0), dim=0)
        return float(probabilities[self.settings.fake_class_index].item())

    def _preprocess_frame(self, frame: np.ndarray):
        # frame is already RGB (shared frame_extraction output)
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
