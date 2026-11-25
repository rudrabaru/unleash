"""Shared test setup.

* The database and the upload/temp directory are redirected to a throwaway folder *before*
  the app is imported, so no test touches ./unleash.db or the real temp directory.
* Short clips for the must-pass audio checks (silence, a tone, a truncated file, garbage
  bytes) are generated with ffmpeg at test time instead of being stored as binaries.
"""
import os
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

_SANDBOX = Path(tempfile.mkdtemp(prefix="unleash_tests_"))
os.environ["ENVIRONMENT"] = "development"  # the production default would refuse to start without a real secret
os.environ["DATABASE_URL"] = "sqlite:///" + (_SANDBOX / "unleash.db").as_posix()
os.environ["UPLOAD_TEMP_DIR"] = str(_SANDBOX / "uploads")
# Tests upload a recording right after creating its session; the "too early" refusal has its own tests.
os.environ["MIN_SUBMIT_SECONDS"] = "0"

from _paths import GENUINE_5WORD_PHRASE, GENUINE_5WORD_WEBM  # noqa: E402  (after the environment is set)


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_SANDBOX, ignore_errors=True)


def pytest_collection_modifyitems(config, items):
    from app.modules.antispoof._config import settings as deepfake_settings

    checkpoint = deepfake_settings.checkpoint_path
    if checkpoint and Path(checkpoint).exists():
        return
    skip = pytest.mark.skip(reason="trained deepfake checkpoint is not present (not stored in git)")
    for item in items:
        if "requires_checkpoint" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Every test gets its own empty database."""
    from app import db

    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "unleash.db")
    db.init_db()


def _ffmpeg(*args):
    exe = shutil.which("ffmpeg")
    assert exe, "ffmpeg is required for the tests (it is also a runtime dependency)"
    subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="session")
def silence_webm(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("clips") / "silence.webm"
    _ffmpeg("-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "5", "-c:a", "libopus", str(out))
    return out


@pytest.fixture(scope="session")
def tone_webm(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("clips") / "tone.webm"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000", "-t", "5", "-c:a", "libopus", str(out))
    return out


@pytest.fixture(scope="session")
def corrupt_webm(tmp_path_factory) -> Path:
    """A valid WebM header followed by a body cut off after 2000 bytes."""
    out = tmp_path_factory.mktemp("clips") / "corrupt.webm"
    out.write_bytes(GENUINE_5WORD_WEBM.read_bytes()[:2000])
    return out


@pytest.fixture(scope="session")
def garbage_webm(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("clips") / "garbage.webm"
    out.write_bytes(random.Random(0).randbytes(8192))
    return out


@pytest.fixture(scope="session")
def browser_recorded_clip(tmp_path_factory):
    """
    Factory: a horizontally flipped copy of a mirror-image sample clip, i.e. what a browser would
    have recorded. The sample direction clips (TURN_LEFT, TURN_RIGHT) were saved the way a selfie
    app shows you (your own left is the left of the picture); a browser records the camera feed
    unmirrored and the backend expects that. Copies are cached for the whole test run.
    """
    folder = tmp_path_factory.mktemp("browser_recorded")

    def make(source: Path) -> Path:
        out = folder / f"{source.stem}_unmirrored.webm"
        if not out.exists():
            _ffmpeg("-i", str(source), "-vf", "hflip", "-an", "-c:v", "libvpx", "-b:v", "4M", str(out))
        return out

    return make


@pytest.fixture(scope="session")
def genuine_wav(tmp_path_factory) -> Path:
    """The genuine 5-word take as the 16 kHz mono WAV the pipeline extracts from it."""
    from app.modules.audio._extraction import extract_wav

    out = tmp_path_factory.mktemp("clips") / "genuine_16k.wav"
    ok, err, _ = extract_wav(GENUINE_5WORD_WEBM, out)
    assert ok, err
    return out


@pytest.fixture(scope="session")
def genuine_pipeline_result():
    """One audio-pipeline run on the genuine take, shared by the tests that only inspect it."""
    from app.modules.audio import process_audio_pipeline

    return process_audio_pipeline(str(GENUINE_5WORD_WEBM), GENUINE_5WORD_PHRASE)


@pytest.fixture(scope="session")
def clap_clip(tmp_path_factory):
    """Factory for a 3 s VP8/Opus clip with a white-frame flash and a 1 kHz tone, both scheduled at t=1.0 s.

    `audio_delay` / `video_delay` shift that track later on the container clock (seconds).
    """
    folder = tmp_path_factory.mktemp("claps")
    video = "color=c=black:s=320x240:r=30:d=3,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(t,1,1.1)'"
    audio = "aevalsrc='if(between(t,1,1.1),0.8*sin(2*PI*1000*t),0)':s=48000:d=3"

    def make(name: str, audio_delay: float = 0.0, video_delay: float = 0.0) -> Path:
        out = folder / f"{name}.webm"
        _ffmpeg(
            "-itsoffset", str(video_delay), "-f", "lavfi", "-i", video,
            "-itsoffset", str(audio_delay), "-f", "lavfi", "-i", audio,
            "-c:v", "libvpx", "-b:v", "1M", "-c:a", "libopus", str(out),
        )
        return out

    return make


@pytest.fixture(scope="session")
def phased_turn_clip(tmp_path_factory):
    """
    Factory for a 13 s browser-style clip of a REAL face that follows the protocol: neutral, then a
    left turn that is held and returned to centre, then neutral again. `turn_at` is the second at
    which the turn begins (8.0 = the start of Act; 2.7 = a turn made during Speak that is over before Act). It is built from the real
    TURN_LEFT sample: its first frame is the neutral pose, the clip itself (sped up 2x) is the turn,
    and the same clip reversed is the return. Everything is flipped to what a browser records
    (the sample is a mirror image). Video only; there is no audio track.
    """
    from _paths import VIDEO_FIXTURES_DIR, require

    folder = tmp_path_factory.mktemp("phased")
    source = require(VIDEO_FIXTURES_DIR / "TURN_LEFT.webm")
    still = folder / "neutral.png"
    _ffmpeg("-i", str(source), "-frames:v", "1", str(still))
    turn_and_return_seconds = 5.24

    def make(turn_at: float) -> Path:
        out = folder / f"turn_at_{turn_at}.webm"
        if out.exists():
            return out
        pad = max(0.0, 13.3 - turn_at - turn_and_return_seconds)
        inputs = ["-loop", "1", "-framerate", "25", "-t", str(turn_at), "-i", str(still), "-i", str(source)]
        graph = (
            "[0:v]hflip,format=yuv420p[a];"
            "[1:v]hflip,setpts=0.5*PTS,fps=25,format=yuv420p,split[t1][t2];[t2]reverse[t3];"
        )
        parts, count = "[a][t1][t3]", 3
        if pad > 0.05:
            inputs += ["-loop", "1", "-framerate", "25", "-t", f"{pad:.2f}", "-i", str(still)]
            graph += "[2:v]hflip,format=yuv420p[p];"
            parts, count = "[a][t1][t3][p]", 4
        graph += f"{parts}concat=n={count}:v=1:a=0[v]"
        _ffmpeg(*inputs, "-filter_complex", graph, "-map", "[v]", "-c:v", "libvpx", "-b:v", "4M", str(out))
        return out

    return make


@pytest.fixture(scope="session")
def phased_speech_clip(tmp_path_factory):
    """
    Factory for an Opus/WebM clip of the genuine 5-word take placed on a protocol timeline: silent
    until `start` seconds, then the take at its own pace, then silent until `total` seconds. The take
    has about a second of silence before its first word and runs 6.1 s, so `start=2.0` puts its speech
    in the Speak window (3-8 s). `keep` cuts the take to its first `keep` seconds. Audio only. (The take
    is not sped up: at 1.25x the recognizer already drops it from 4 to 2 of 5 words.)
    """
    from _paths import GENUINE_5WORD_WEBM, require

    folder = tmp_path_factory.mktemp("phased_speech")
    source = require(GENUINE_5WORD_WEBM)

    def make(start: float, keep: float = None, total: float = 16.0) -> Path:
        out = folder / f"take_at_{start}_keep_{keep}.webm"
        if not out.exists():
            trim = f"atrim=end={keep}," if keep else ""
            _ffmpeg(
                "-i", str(source), "-ac", "1", "-af",
                f"{trim}adelay={int(round(start * 1000))},apad=whole_dur={total}", "-c:a", "libopus", str(out),
            )
        return out

    return make


@pytest.fixture(scope="session")
def protocol_take(phased_turn_clip, phased_speech_clip, tmp_path_factory):
    """
    A 13 s recording that follows the protocol: a REAL face that turns left in Act (video from
    `phased_turn_clip`) and a REAL spoken 5-word take in Speak (audio from `phased_speech_clip`),
    muxed into one WebM like a browser recording. The face and the voice are different people's
    samples, so lip sync means nothing here; every other part of the pipeline is real.
    """
    out = tmp_path_factory.mktemp("protocol_take") / "protocol_take.webm"
    _ffmpeg(
        "-i", str(phased_turn_clip(8.0)), "-i", str(phased_speech_clip(2.0, total=13.3)),
        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy", "-shortest", str(out),
    )
    return out


def _mux(out: Path, video: Path, audio: Path, video_offset: float = 0.0) -> Path:
    """One WebM from a video file and an audio file; `video_offset` makes the picture start that many seconds late."""
    _ffmpeg(
        "-itsoffset", str(video_offset), "-i", str(video), "-i", str(audio),
        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy", "-shortest", str(out),
    )
    return out


@pytest.fixture(scope="session")
def protocol_take_with_silent_microphone(phased_turn_clip, tmp_path_factory):
    """A protocol-length recording of a real turning face whose microphone recorded digital silence."""
    folder = tmp_path_factory.mktemp("silent_mic")
    silence = folder / "silence.webm"
    _ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "13.5", "-c:a", "libopus", str(silence))
    return _mux(folder / "silent_mic.webm", phased_turn_clip(8.0), silence)


@pytest.fixture(scope="session")
def protocol_take_without_a_face(phased_speech_clip, tmp_path_factory):
    """A protocol-length recording with the real spoken take over a plain dark picture: nobody in front of the camera."""
    folder = tmp_path_factory.mktemp("no_face")
    picture = folder / "dark.webm"
    _ffmpeg("-f", "lavfi", "-i", "color=c=0x202020:s=640x480:r=25:d=13.5", "-c:v", "libvpx", str(picture))
    return _mux(folder / "no_face.webm", picture, phased_speech_clip(2.0, total=13.5))


@pytest.fixture(scope="session")
def protocol_take_with_late_picture(phased_turn_clip, phased_speech_clip, tmp_path_factory):
    """A recording whose picture starts a full second after its sound: the windows would name different moments."""
    return _mux(
        tmp_path_factory.mktemp("late_picture") / "late_picture.webm",
        phased_turn_clip(8.0), phased_speech_clip(2.0, total=13.3), video_offset=1.0,
    )


@pytest.fixture(scope="session")
def oversized_picture_webm(tmp_path_factory):
    """A one-second clip whose picture is 2560x1440, larger than the 1920x1080 a recording may have."""
    out = tmp_path_factory.mktemp("oversized") / "big_picture.webm"
    _ffmpeg("-f", "lavfi", "-i", "color=c=black:s=2560x1440:r=5:d=1", "-c:v", "libvpx", str(out))
    return out


@pytest.fixture(scope="session")
def long_recording_webm(tmp_path_factory):
    """A 40 s audio recording, longer than the 30 s a recording may have."""
    out = tmp_path_factory.mktemp("long") / "forty_seconds.webm"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=300:sample_rate=16000", "-t", "40", "-c:a", "libopus", str(out))
    return out
