"""
Audio I/O and Resampling Utilities.

Centralized helpers for reading, validating, and converting WAV audio files
to tensor (PyTorch) or ndarray (NumPy) representations at 16kHz mono float32.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple

import numpy as np
import soundfile as sf
import torch

logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000


def read_wav_numpy(path: Path | str) -> Tuple[np.ndarray, int, float]:
    """
    Read WAV audio into float32 1D numpy array.
    
    Converts multi-channel to mono via channel averaging.
    Returns:
        (audio_data, sample_rate, duration_seconds)
    """
    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = np.mean(data, axis=1)
    duration = len(data) / float(sr) if sr > 0 else 0.0
    return data, sr, duration


def read_wav_torch(path: Path | str) -> Tuple[torch.Tensor, float]:
    """
    Read 16kHz mono WAV audio into a 1D PyTorch float32 tensor.
    
    Raises:
        ValueError: If sample rate is not TARGET_SAMPLE_RATE (16000Hz).
    Returns:
        (audio_tensor, duration_seconds)
    """
    data, sr, duration = read_wav_numpy(path)
    if sr != TARGET_SAMPLE_RATE:
        raise ValueError(f"Expected sample rate {TARGET_SAMPLE_RATE}Hz, got {sr}Hz")
    tensor = torch.from_numpy(np.ascontiguousarray(data))
    return tensor, duration
