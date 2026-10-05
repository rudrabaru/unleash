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
os.environ["DATABASE_URL"] = "sqlite:///" + (_SANDBOX / "unleash.db").as_posix()
os.environ["UPLOAD_TEMP_DIR"] = str(_SANDBOX / "uploads")

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
