"""
Integration tests: real detectors on real clips through the shared analysis entry point and the
development-only demo endpoint. They check that the modules fit together, not that any signal
is accurate.
"""
import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app import orchestrator
from app.core.config import settings
from app.main import app
from app.schemas.detector import DetectorResult
from _paths import (
    GENUINE_5WORD_NOFACE_VIDEO_WEBM,
    GENUINE_5WORD_PHRASE,
    VIDEO_FIXTURES_DIR,
    require,
)

SIGNALS = {"audio_pipeline", "visual_liveness", "visual_challenge", "deepfake", "replay"}
client = TestClient(app)


def _assert_contract(signals):
    assert set(signals) == SIGNALS
    for name, result in signals.items():
        assert isinstance(result, DetectorResult), name
        assert isinstance(result.passed, bool) and result.reason, name
        if result.error is not None:
            assert result.score is None, f"{name} returned a score together with an error"


def test_video_without_audio_fails_on_the_audio_check():
    """A clip with a face turning left but no audio track: every signal is present, audio fails."""
    clip = require(VIDEO_FIXTURES_DIR / "TURN_LEFT.webm")

    analysis = asyncio.run(orchestrator.analyze_media(clip, "TURN_HEAD_LEFT", GENUINE_5WORD_PHRASE))

    _assert_contract(analysis.signals)
    assert analysis.signals["visual_challenge"].passed is True
    assert analysis.signals["audio_pipeline"].passed is False
    assert analysis.fusion.status.value == "FAILED"
    assert analysis.fusion.reason.startswith("Audio hard gate failed")


def test_genuine_speech_on_a_video_without_a_face_fails_on_the_visual_challenge():
    clip = require(GENUINE_5WORD_NOFACE_VIDEO_WEBM)

    analysis = asyncio.run(orchestrator.analyze_media(clip, "TURN_HEAD_LEFT", GENUINE_5WORD_PHRASE))

    _assert_contract(analysis.signals)
    assert analysis.signals["audio_pipeline"].passed is True
    assert analysis.signals["visual_challenge"].passed is False
    assert analysis.fusion.status.value == "FAILED"
    assert analysis.fusion.reason.startswith("Visual challenge compliance failed")


def _post(clip: Path, filename: str = "clip.webm", visual: str = "TURN_HEAD_LEFT"):
    with open(clip, "rb") as f:
        return client.post(
            "/api/v1/verify",
            data={"visual_challenge": visual, "verbal_challenge": GENUINE_5WORD_PHRASE},
            files={"video": (filename, f, "video/webm")},
        )


def test_verify_endpoint_returns_every_signal_the_verdict_and_timings():
    response = _post(require(GENUINE_5WORD_NOFACE_VIDEO_WEBM))

    assert response.status_code == 200
    body = response.json()
    assert set(body["signals"]) == SIGNALS
    assert body["status"] == "FAILED"
    assert body["signals"]["audio_pipeline"]["passed"] is True
    assert "total" in body["timings"]


def test_verify_endpoint_deletes_the_uploaded_file():
    _post(require(GENUINE_5WORD_NOFACE_VIDEO_WEBM))

    leftovers = [p.name for p in Path(settings.UPLOAD_TEMP_DIR).glob("verify_*")]
    assert leftovers == []


def test_verify_endpoint_rejects_an_unsupported_format():
    response = _post(require(GENUINE_5WORD_NOFACE_VIDEO_WEBM), filename="clip.txt")

    assert response.status_code == 400


def test_verify_endpoint_is_disabled_outside_development(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    response = _post(require(GENUINE_5WORD_NOFACE_VIDEO_WEBM))

    assert response.status_code == 404
