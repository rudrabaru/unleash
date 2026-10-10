"""
The recording timeline probe (app.media.probe): where each track starts and ends and how big the
picture is, read from packets only.
"""
import pytest

from app.media.probe import probe_streams
from _paths import GENUINE_5WORD_NOFACE_VIDEO_WEBM, GENUINE_5WORD_WEBM, require


def test_an_audio_only_take_has_an_audio_timeline_and_no_picture():
    probe = probe_streams(require(GENUINE_5WORD_WEBM))

    assert probe.error is None
    assert probe.video is None and probe.width is None and probe.height is None
    assert probe.audio is not None and probe.audio.last > probe.audio.first
    assert probe.recording_start == pytest.approx(max(0.0, probe.audio.first))
    assert probe.duration > 1.0


def test_a_browser_style_video_has_both_tracks_and_a_picture_size():
    probe = probe_streams(require(GENUINE_5WORD_NOFACE_VIDEO_WEBM))

    assert probe.error is None
    assert probe.video is not None and probe.audio is not None
    assert probe.width > 0 and probe.height > 0


def test_the_recording_starts_at_the_earliest_track_whichever_it_is(clap_clip):
    audio_late = probe_streams(clap_clip("probe_audio_late", audio_delay=0.3))
    video_late = probe_streams(clap_clip("probe_video_late", video_delay=0.3))

    assert audio_late.audio.first == pytest.approx(0.3, abs=0.06)
    assert audio_late.video.first == pytest.approx(0.0, abs=0.06)
    assert audio_late.recording_start == pytest.approx(0.0, abs=0.06)
    assert video_late.video.first == pytest.approx(0.3, abs=0.06)
    assert video_late.recording_start == pytest.approx(0.0, abs=0.06)


def test_duration_runs_from_the_recording_start_to_the_last_packet(clap_clip):
    probe = probe_streams(clap_clip("probe_plain"))  # 3 s clip

    assert probe.duration == pytest.approx(3.0, abs=0.15)


def test_a_file_longer_than_the_limit_is_cut_short_and_flagged(tone_webm):
    probe = probe_streams(tone_webm, limit_seconds=1.0)  # a 5 s tone

    assert probe.over_limit is True
    assert probe.audio is not None and probe.audio.last < 2.0  # stopped reading long before the end


def test_a_file_within_the_limit_is_read_to_the_end(tone_webm):
    probe = probe_streams(tone_webm, limit_seconds=30.0)

    assert probe.over_limit is False
    assert probe.duration == pytest.approx(5.0, abs=0.2)


def test_garbage_and_missing_files_come_back_as_an_error_not_an_exception(garbage_webm, tmp_path):
    for path in (garbage_webm, tmp_path / "missing.webm"):
        probe = probe_streams(path)
        assert probe.error
        assert probe.recording_start is None and probe.duration is None
