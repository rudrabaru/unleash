"""
Integration tests for the sessions API.
Tests real background analysis through HTTP requests.
"""
from __future__ import annotations

import secrets

from fastapi.testclient import TestClient

from app import db
from app.core.config import settings
from app.core.security import generate_challenge_token
from app.api.v1.endpoints import sessions
from app.main import app
from app.schemas.session import VerificationStatus
from _paths import (
    GENUINE_5WORD_NOFACE_VIDEO_WEBM,
    GENUINE_5WORD_PHRASE,
    OTHER_5WORD_PHRASE,
    require,
)

client = TestClient(app)


def _create_session_with_phrase(phrase: str):
    """Create a session through the API, then pin its verbal challenge to `phrase`."""
    create_resp = client.post("/api/v1/sessions")
    assert create_resp.status_code == 201
    session_id = create_resp.json()["session_id"]
    db.set_challenge(session_id, verbal_challenge=phrase)
    session = db.get_session(session_id)
    token, _ = generate_challenge_token(
        session_id=session_id,
        visual_challenge=session["visual_challenge"],
        verbal_challenge=phrase,
        secret_key=settings.SECRET_KEY,
        expiry_seconds=60,
    )
    return session_id, token


def _submit(session_id: str, token: str, media_path):
    with open(media_path, "rb") as f:
        return client.post(
            f"/api/v1/sessions/{session_id}/submit",
            data={"token": token},
            files={"media": ("recording.webm", f, "video/webm")},
        )


def test_session_lifecycle_with_real_audio_verification():
    """
    Full session creation, submit and background analysis with a genuine take of the 5-word
    challenge. `genuine_5word_noface_video.webm` pairs that audio with a video track that has
    no face, so the session correctly comes back FAILED through the visual challenge check
    even though every audio-side assertion passes. A VERIFIED case needs a recording with a
    compliant face.
    """
    media = require(GENUINE_5WORD_NOFACE_VIDEO_WEBM)
    session_id, token = _create_session_with_phrase(GENUINE_5WORD_PHRASE)

    assert _submit(session_id, token, media).status_code == 202

    # TestClient runs background tasks synchronously
    result_resp = client.get(f"/api/v1/sessions/{session_id}")
    assert result_resp.status_code == 200
    res_data = result_resp.json()

    assert res_data["status"] == VerificationStatus.FAILED
    assert res_data["signals"]["audio_pipeline"]["passed"] is True
    assert res_data["signals"]["audio_pipeline"]["details"]["phrase_matched"] is True
    assert res_data["signals"]["visual_challenge"]["passed"] is False

    audio_details = res_data["signals"]["audio_pipeline"]["details"]
    assert isinstance(audio_details["voice_authenticity_score"], float)
    # a video track with no face gives no lip series, so the lip-sync check has no score
    assert audio_details.get("av_alignment_score") is None


def test_session_lifecycle_with_wrong_challenge_fails():
    """Speech that does not match the issued challenge fails the audio check."""
    media = require(GENUINE_5WORD_NOFACE_VIDEO_WEBM)
    session_id, token = _create_session_with_phrase(OTHER_5WORD_PHRASE)

    assert _submit(session_id, token, media).status_code == 202

    res_data = client.get(f"/api/v1/sessions/{session_id}").json()
    assert res_data["status"] == VerificationStatus.FAILED
    assert res_data["signals"]["audio_pipeline"]["passed"] is False


def test_submit_loses_when_another_request_claimed_the_session_first(monkeypatch):
    """The CREATED -> PROCESSING change is one atomic update; the request that loses it gets 409."""
    media = require(GENUINE_5WORD_NOFACE_VIDEO_WEBM)
    session_id, token = _create_session_with_phrase(GENUINE_5WORD_PHRASE)
    monkeypatch.setattr(db, "claim_for_processing", lambda *args, **kwargs: False)

    assert _submit(session_id, token, media).status_code == 409


def test_challenge_selection_uses_the_os_csprng():
    assert isinstance(sessions._rng, secrets.SystemRandom)
