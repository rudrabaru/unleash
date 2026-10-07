"""
Unit tests for audio I/O utilities (_io.py).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import torch

from app.modules.audio._io import TARGET_SAMPLE_RATE, read_wav_numpy, read_wav_torch


def test_read_wav_numpy_mono(tmp_path: Path):
    """Test reading 16kHz mono WAV file returns correct numpy array and duration."""
    sr = TARGET_SAMPLE_RATE
    duration_s = 1.5
    data = np.sin(2 * np.pi * 440 * np.linspace(0, duration_s, int(sr * duration_s))).astype(np.float32)
    wav_path = tmp_path / "mono.wav"
    sf.write(str(wav_path), data, sr)

    arr, read_sr, dur = read_wav_numpy(wav_path)
    assert isinstance(arr, np.ndarray)
    assert arr.ndim == 1
    assert read_sr == TARGET_SAMPLE_RATE
    assert pytest.approx(dur, 0.01) == duration_s
    assert len(arr) == int(sr * duration_s)


def test_read_wav_numpy_stereo_to_mono(tmp_path: Path):
    """Test reading stereo WAV averages channels to 1D mono."""
    sr = TARGET_SAMPLE_RATE
    duration_s = 1.0
    stereo_data = np.ones((int(sr * duration_s), 2), dtype=np.float32)
    wav_path = tmp_path / "stereo.wav"
    sf.write(str(wav_path), stereo_data, sr)

    arr, read_sr, dur = read_wav_numpy(wav_path)
    assert arr.ndim == 1
    assert len(arr) == int(sr * duration_s)


def test_read_wav_torch_valid(tmp_path: Path):
    """Test reading valid 16kHz WAV into PyTorch float32 tensor."""
    sr = TARGET_SAMPLE_RATE
    duration_s = 2.0
    data = np.zeros(int(sr * duration_s), dtype=np.float32)
    wav_path = tmp_path / "tensor_test.wav"
    sf.write(str(wav_path), data, sr)

    tensor, dur = read_wav_torch(wav_path)
    assert isinstance(tensor, torch.Tensor)
    assert tensor.dtype == torch.float32
    assert tensor.ndim == 1
    assert pytest.approx(dur, 0.01) == duration_s


def test_read_wav_torch_invalid_sample_rate(tmp_path: Path):
    """Test that read_wav_torch raises ValueError for non-16kHz audio."""
    sr = 44100
    data = np.zeros(sr, dtype=np.float32)
    wav_path = tmp_path / "invalid_sr.wav"
    sf.write(str(wav_path), data, sr)

    with pytest.raises(ValueError, match=f"Expected sample rate {TARGET_SAMPLE_RATE}Hz"):
        read_wav_torch(wav_path)


def test_read_wav_numpy_require_16k(tmp_path: Path):
    """Test that read_wav_numpy with require_16k=True enforces 16kHz."""
    sr = 44100
    data = np.zeros(sr, dtype=np.float32)
    wav_path = tmp_path / "non_16k.wav"
    sf.write(str(wav_path), data, sr)

    # Permissive by default
    arr, read_sr, _ = read_wav_numpy(wav_path, require_16k=False)
    assert read_sr == 44100
    assert len(arr) == 44100

    # Strict when require_16k=True
    with pytest.raises(ValueError, match=f"Expected sample rate {TARGET_SAMPLE_RATE}Hz"):
        read_wav_numpy(wav_path, require_16k=True)

