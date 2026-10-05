"""
Video times and audio times must be on one clock, because the lip-sync check compares the lip
series (container clock) with the spoken-word times (relative to the extracted WAV).

The synthetic clips have a white flash and a tone burst both scheduled at t=1.0 s. They show
that the extracted WAV loses the audio track's start offset, and that adding the audio start
(`to_container_time`) restores one clock.
"""
from unittest.mock import patch

import numpy as np
import pytest

from app.media.frames import load_frames
from app.modules.audio import process_audio_pipeline
from app.modules.audio._av_alignment import to_container_time
from app.modules.audio._extraction import extract_wav, probe_media
from app.modules.audio._io import read_wav_numpy
from app.schemas.detector import DetectorResult
from _paths import OTHER_5WORD_PHRASE


def _flash_time(path) -> float:
    bundle = load_frames(path)
    assert bundle.error is None, bundle.error
    return next(t for frame, t in zip(bundle.dense, bundle.dense_times) if frame.mean() > 128)


def _tone_time_in_wav(path, tmp_path) -> float:
    wav = tmp_path / "tone_16k.wav"
    ok, err, _ = extract_wav(path, wav)
    assert ok, err
    samples, rate, _ = read_wav_numpy(wav)
    return float(np.argmax(np.abs(samples) > 0.1)) / rate


def test_aligned_clip_has_flash_and_tone_at_the_same_time(clap_clip, tmp_path):
    clip = clap_clip("aligned")

    assert _flash_time(clip) == pytest.approx(1.0, abs=0.05)
    assert _tone_time_in_wav(clip, tmp_path) == pytest.approx(1.0, abs=0.05)
    assert max(0.0, probe_media(clip)["audio"]["start_time"]) == pytest.approx(0.0, abs=0.02)


def test_extracted_audio_loses_a_late_audio_start_but_the_probe_reports_it(clap_clip, tmp_path):
    """The tone is 0.3 s after the flash on the container clock, yet the WAV places it at 1.0 s."""
    clip = clap_clip("audio_late", audio_delay=0.3)

    assert _flash_time(clip) == pytest.approx(1.0, abs=0.05)
    assert _tone_time_in_wav(clip, tmp_path) == pytest.approx(1.0, abs=0.05)  # offset lost in the WAV
    audio_start = probe_media(clip)["audio"]["start_time"]
    assert audio_start == pytest.approx(0.3, abs=0.03)  # ... but the container says where the audio starts
    assert _tone_time_in_wav(clip, tmp_path) + max(0.0, audio_start) == pytest.approx(1.3, abs=0.05)


def test_a_late_video_start_is_already_on_the_container_clock(clap_clip, tmp_path):
    clip = clap_clip("video_late", video_delay=0.3)

    assert _flash_time(clip) == pytest.approx(1.3, abs=0.05)
    assert _tone_time_in_wav(clip, tmp_path) == pytest.approx(1.0, abs=0.05)


def test_to_container_time_shifts_words_by_the_audio_start():
    words = [{"word": "a", "start": 1.0, "end": 1.4, "probability": 0.9}]

    shifted = to_container_time(words, 0.3)

    assert shifted == [{"word": "a", "start": pytest.approx(1.3), "end": pytest.approx(1.7), "probability": 0.9}]
    assert words[0]["start"] == 1.0  # the original is left untouched
    assert to_container_time(words, -0.007)[0]["start"] == 1.0  # the Opus pre-skip is not an offset
    assert to_container_time(None, 0.3) is None


def test_the_pipeline_gives_the_lip_sync_check_words_on_the_container_clock(clap_clip):
    clip = clap_clip("audio_late", audio_delay=0.3)
    words = [{"word": "walnut", "start": 1.0, "end": 1.4, "probability": 0.9}]
    speech = DetectorResult(score=None, passed=True, reason="speech", details={"speech_detected": True, "segments": []})
    phrase = DetectorResult(score=1.0, passed=True, reason="phrase", details={"word_timestamps": words, "match_count": 5})
    voice = DetectorResult(score=0.5, passed=True, reason="voice", details={"voice_authenticity_score": 0.5})
    lip_sync = DetectorResult(score=None, passed=True, reason="lip sync", details={})

    with patch("app.modules.audio.run_speech_gate", return_value=speech), \
         patch("app.modules.audio.run_phrase_compliance", return_value=phrase), \
         patch("app.modules.audio.run_voice_authenticity", return_value=voice), \
         patch("app.modules.audio.run_av_alignment", return_value=lip_sync) as lip_sync_check:
        result = process_audio_pipeline(str(clip), OTHER_5WORD_PHRASE)

    passed_words = lip_sync_check.call_args.kwargs["word_timestamps"]
    assert passed_words[0]["start"] == pytest.approx(1.3, abs=0.03)
    assert result.details["audio_start_offset_seconds"] == pytest.approx(0.3, abs=0.03)
