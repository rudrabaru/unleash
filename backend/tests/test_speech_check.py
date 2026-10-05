"""
Tests for the speech check (voice-activity detection) and the audio extraction that feeds it.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import soundfile as sf

from app.modules.audio import process_audio_pipeline
from app.modules.audio._extraction import check_extraction_completeness, verify_wav
from app.modules.audio._speech_gate import (
    SPEECH_DURATION_THRESHOLD_S,
    TARGET_SAMPLE_RATE,
    _VAD_MODEL,
    run_speech_gate,
)
from app.schemas.detector import DetectorResult
from _paths import OTHER_5WORD_PHRASE


def test_vad_model_loaded():
    """The silero-vad model is loaded once at module initialization."""
    assert _VAD_MODEL is not None, "VAD model should be loaded at module initialization"


def test_silence_rejected(tmp_path):
    """Silence is rejected by the speech check (speech_detected=False, passed=False)."""
    wav = tmp_path / "silence.wav"
    sf.write(str(wav), np.zeros(TARGET_SAMPLE_RATE * 5, dtype=np.float32), TARGET_SAMPLE_RATE)

    res = run_speech_gate(wav)
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.error is None
    assert res.score is None
    assert res.details is not None
    assert res.details.get("speech_detected") is False
    assert res.details.get("speech_duration_seconds") == 0.0


def test_tone_rejected(tmp_path):
    """Non-speech audio (a sine tone) is rejected by the speech check."""
    t = np.linspace(0, 5.0, TARGET_SAMPLE_RATE * 5, endpoint=False)
    wav = tmp_path / "tone.wav"
    sf.write(str(wav), (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), TARGET_SAMPLE_RATE)

    res = run_speech_gate(wav)
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.error is None
    assert res.score is None
    assert res.details is not None
    assert res.details.get("speech_detected") is False


def test_empty_wav_handled(tmp_path):
    """An empty WAV file is handled gracefully without crashing."""
    wav = tmp_path / "empty.wav"
    sf.write(str(wav), np.array([], dtype=np.float32), TARGET_SAMPLE_RATE)

    res = run_speech_gate(wav)
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None


def test_corrupt_wav_file_handled(tmp_path):
    """Non-WAV bytes do not cause an uncaught exception."""
    wav = tmp_path / "corrupt.wav"
    wav.write_bytes(b"NOT_A_REAL_WAV_HEADER_DATA_1234567890")

    res = run_speech_gate(wav)
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None
    assert res.error is not None


def test_nonexistent_file_handled():
    """A missing file does not raise an uncaught exception."""
    res = run_speech_gate(Path("this_file_definitely_does_not_exist_12345.wav"))
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None
    assert res.error is not None


def test_extraction_completeness_checker():
    """check_extraction_completeness tells truncated extractions from valid ones."""
    ok, err = check_extraction_completeness(5.0, 5.0)
    assert ok is True
    assert err is None

    # Minor boundary variance (95%) is fine
    ok, err = check_extraction_completeness(6.0, 5.7)
    assert ok is True
    assert err is None

    # Severe truncation (below the 50% threshold): ffmpeg exits 0 yet loses most of the audio
    ok, err = check_extraction_completeness(5.0, 0.5)
    assert ok is False
    assert "truncated" in err.lower() or "below" in err.lower()

    # A container with no duration header (common for browser recordings) skips the ratio check
    ok, err = check_extraction_completeness(None, 4.2)
    assert ok is True
    assert err is None


def test_verify_wav_contract(tmp_path):
    """verify_wav enforces the 16 kHz mono contract."""
    mono_16k = tmp_path / "mono_16k.wav"
    stereo_44k = tmp_path / "stereo_44k.wav"
    sf.write(str(mono_16k), np.zeros(16000, dtype=np.float32), 16000)
    sf.write(str(stereo_44k), np.zeros((44100, 2), dtype=np.float32), 44100)

    ok, _ = verify_wav(mono_16k)
    assert ok is True

    ok, desc = verify_wav(stereo_44k)
    assert ok is False
    assert "violated" in desc.lower()


def test_pipeline_with_real_speech_fixture(genuine_pipeline_result):
    """The full audio pipeline passes a genuine take of the 5-word challenge."""
    res = genuine_pipeline_result
    assert isinstance(res, DetectorResult)
    assert res.passed is True
    assert res.error is None
    assert res.score is not None and res.score >= 0.6
    assert res.details is not None
    assert res.details["speech_detected"] is True
    assert res.details["speech_duration_seconds"] >= SPEECH_DURATION_THRESHOLD_S


def test_pipeline_with_silence(silence_webm):
    """Muted microphone: the speech check stops the pipeline."""
    res = asyncio.run(process_audio_pipeline(str(silence_webm), OTHER_5WORD_PHRASE))
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None
    assert res.error is None
    assert res.details["speech_detected"] is False


def test_pipeline_with_non_speech_tone(tone_webm):
    """Music or a tone near the microphone is not speech."""
    res = asyncio.run(process_audio_pipeline(str(tone_webm), OTHER_5WORD_PHRASE))
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None
    assert res.error is None
    assert res.details["speech_detected"] is False


def test_pipeline_with_truncated_file(corrupt_webm):
    """A valid header with a cut-off body fails cleanly."""
    res = asyncio.run(process_audio_pipeline(str(corrupt_webm), OTHER_5WORD_PHRASE))
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None


def test_pipeline_with_garbage_bytes(garbage_webm):
    """Random bytes fail cleanly with an error and no score."""
    res = asyncio.run(process_audio_pipeline(str(garbage_webm), OTHER_5WORD_PHRASE))
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None
    assert res.error is not None
