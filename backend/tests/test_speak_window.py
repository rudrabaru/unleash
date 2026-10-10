"""
The audio checks with the protocol windows: speech and phrase are judged inside the Speak window only,
and every time is put back on the right clock.
"""
import numpy as np
import pytest
import soundfile as sf

from app.media.probe import probe_streams
from app.modules.audio import _trim_lip_series, process_audio_pipeline
from app.modules.audio._speak_crop import SpeakCrop, plan_speak_crop, write_speak_crop
from app.protocol import PROTOCOL_V1
from _paths import GENUINE_5WORD_PHRASE


def _run(clip, **kwargs):
    start = probe_streams(clip).recording_start
    return process_audio_pipeline(str(clip), GENUINE_5WORD_PHRASE, phases=PROTOCOL_V1, recording_start=start, **kwargs)


# --- the crop arithmetic -------------------------------------------------------------------------

def test_the_speech_window_is_speak_plus_the_guard_and_the_trailing_allowance():
    assert PROTOCOL_V1.speech_window() == pytest.approx((2.6, 8.7))


def test_the_crop_lies_where_the_window_is_on_the_extracted_audio():
    plain = plan_speak_crop(PROTOCOL_V1, recording_start=0.0, audio_start=0.0)
    late_audio = plan_speak_crop(PROTOCOL_V1, recording_start=0.0, audio_start=0.3)
    shifted_clock = plan_speak_crop(PROTOCOL_V1, recording_start=0.5, audio_start=0.5)

    assert (plain.wav_start, plain.wav_end) == pytest.approx((2.6, 8.7))
    assert (late_audio.wav_start, late_audio.wav_end) == pytest.approx((2.3, 8.4))  # the WAV lost the 0.3 s
    assert (late_audio.container_start, late_audio.container_end) == pytest.approx((2.6, 8.7))
    assert (shifted_clock.wav_start, shifted_clock.wav_end) == pytest.approx((2.6, 8.7))
    assert shifted_clock.container_start == pytest.approx(3.1)


def test_a_crop_never_starts_before_the_audio_does():
    crop = plan_speak_crop(PROTOCOL_V1, recording_start=0.0, audio_start=5.0)

    assert crop.wav_start == 0.0 and crop.wav_end == pytest.approx(3.7)


def test_the_cropped_file_holds_exactly_the_window(tmp_path):
    wav = tmp_path / "ten_seconds.wav"
    sf.write(str(wav), np.zeros(160000, dtype=np.float32), 16000)
    crop = SpeakCrop(wav_start=2.0, wav_end=5.5, container_start=2.0, container_end=5.5)

    out = write_speak_crop(wav, crop, tmp_path / "speak.wav")

    assert sf.info(str(out)).frames == 56000 and sf.info(str(out)).samplerate == 16000


def test_the_lip_series_is_trimmed_to_the_window_with_a_margin():
    crop = SpeakCrop(wav_start=2.6, wav_end=8.7, container_start=2.6, container_end=8.7)
    series = [{"time_seconds": t / 2, "lip_openness_ratio": 0.0} for t in range(0, 30)]  # 0 .. 14.5 s

    trimmed = _trim_lip_series({"fps": 30.0, "series": series}, crop)

    times = [s["time_seconds"] for s in trimmed["series"]]
    assert min(times) == 2.5 and max(times) == 9.0  # 2.6 - 0.5 and 8.7 + 0.5, on the half-second grid
    assert _trim_lip_series({"fps": 30.0, "series": series}, None)["series"] == series


# --- the checks on real speech -------------------------------------------------------------------

def test_a_take_inside_the_speak_window_passes_and_reports_the_window(phased_speech_clip):
    result = _run(phased_speech_clip(2.0))

    assert result.passed is True, result.reason
    assert result.details["match_count"] >= 4 and result.details["insertions"] <= 3
    window = result.details["speak_window"]
    assert window["container_start"] == pytest.approx(2.6, abs=0.1)
    assert window["audio_seconds"] == pytest.approx(6.1, abs=0.2)


def test_the_same_take_spoken_after_the_window_is_not_heard(phased_speech_clip):
    late = phased_speech_clip(9.0)  # the speech itself starts a second later, in Act

    with_windows = _run(late)
    whole_recording = process_audio_pipeline(str(late), GENUINE_5WORD_PHRASE)

    assert with_windows.passed is False
    assert with_windows.details["speech_detected"] is False or with_windows.details["speech_duration_seconds"] < 2.0
    # Without windows the speech is counted wherever it is: the old behaviour (whether the recognizer then
    # gets every word is a separate matter, so only the speech check is asserted here).
    assert whole_recording.details["speech_detected"] is True
    assert whole_recording.details["speech_duration_seconds"] >= 2.0


def test_the_same_take_spoken_before_the_window_is_not_heard(phased_speech_clip):
    early = phased_speech_clip(0.0, keep=2.4)  # the first two words, read aloud during Read

    result = _run(early)

    assert result.passed is False
    assert result.details["speech_detected"] is False


def test_word_times_land_on_the_container_clock_so_lip_sync_finds_the_mouth(phased_speech_clip):
    """
    A mouth that opens exactly while each word is said, on the container clock. If the crop's offsets
    were wrong by even a second the words would meet closed-mouth samples and the score would drop.
    """
    clip = phased_speech_clip(2.0)
    heard = _run(clip)
    spoken = [(w["start"], w["end"]) for w in heard.details["word_timestamps"]]
    crop_origin = heard.details["speak_window"]["container_start"]

    def series(shift):
        samples = []
        for i in range(0, 140):  # 10 Hz over 14 s on the container clock
            t = i / 10
            open_now = any(crop_origin + a - 0.05 <= t - shift <= crop_origin + b + 0.05 for a, b in spoken)
            samples.append({"frame_index": i, "time_seconds": t, "lip_openness_ratio": 0.08 if open_now else 0.0})
        return {"fps": 10.0, "series": samples}

    aligned = _run(clip, lip_openness_data=series(0.0)).details["av_alignment_score"]
    off_by_two_seconds = _run(clip, lip_openness_data=series(2.0)).details["av_alignment_score"]

    assert aligned is not None and aligned >= 0.8
    assert off_by_two_seconds is None or off_by_two_seconds < aligned
