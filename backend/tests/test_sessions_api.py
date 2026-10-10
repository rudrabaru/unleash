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
    require,
)

client = TestClient(app)


def _create_session_with_phrase(phrase: str):
    """Create a session through the API, then pin its verbal challenge to `phrase`."""
    create_resp = client.post("/api/v1/sessions")
    assert create_resp.status_code == 201
    session_id = create_resp.json()["session_id"]
    with db._connect() as conn:  # pin the random challenge to the phrase the fixture speaks
        conn.execute("UPDATE sessions SET verbal_challenge = ? WHERE session_id = ?", (phrase, session_id))
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


def test_session_lifecycle_judges_a_protocol_recording_through_every_check(protocol_take):
    """
    Full session creation, submit and background analysis on a recording that follows the protocol: a
    real face that turns left, holds and returns in Act, and a real spoken 5-word take in Speak. Both
    must-pass checks pass, so the verdict is decided by the weighted signals (a VERIFIED case is not
    asserted: the anti-spoofing scores are uncalibrated).
    """
    session_id, token = _create_session_with_phrase(GENUINE_5WORD_PHRASE)
    with db._connect() as conn:  # the face in the recording turns left
        conn.execute("UPDATE sessions SET visual_challenge = ? WHERE session_id = ?", ("TURN_HEAD_LEFT", session_id))
    token, _ = generate_challenge_token(
        session_id=session_id, visual_challenge="TURN_HEAD_LEFT", verbal_challenge=GENUINE_5WORD_PHRASE,
        secret_key=settings.SECRET_KEY, expiry_seconds=60,
    )

    assert _submit(session_id, token, protocol_take).status_code == 202

    # TestClient runs background tasks synchronously
    res_data = client.get(f"/api/v1/sessions/{session_id}").json()

    signals = res_data["signals"]
    assert signals["audio_pipeline"]["passed"] is True, signals["audio_pipeline"]["reason"]
    assert signals["audio_pipeline"]["details"]["phrase_matched"] is True
    assert signals["audio_pipeline"]["details"]["speak_window"] is not None  # judged inside the window
    assert signals["visual_challenge"]["passed"] is True, signals["visual_challenge"]["reason"]
    assert signals["visual_challenge"]["details"]["phase_aware"] is True
    assert isinstance(signals["audio_pipeline"]["details"]["voice_authenticity_score"], float)
    assert res_data["status"] != VerificationStatus.FAILED or "must-pass" not in res_data["decision_reason"]


def test_submit_loses_when_another_request_claimed_the_session_first(monkeypatch):
    """The CREATED -> PROCESSING change is one atomic update; the request that loses it gets 409."""
    media = require(GENUINE_5WORD_NOFACE_VIDEO_WEBM)
    session_id, token = _create_session_with_phrase(GENUINE_5WORD_PHRASE)
    monkeypatch.setattr(db, "claim_for_processing", lambda *args, **kwargs: False)

    assert _submit(session_id, token, media).status_code == 409


def test_challenge_selection_uses_the_os_csprng():
    assert isinstance(sessions._rng, secrets.SystemRandom)


# --- answers the API gives when something is wrong with the request ------------------------------

def test_an_unknown_session_is_a_404_for_both_reading_and_submitting():
    assert client.get("/api/v1/sessions/does-not-exist").status_code == 404
    response = client.post(
        "/api/v1/sessions/does-not-exist/submit", data={"token": "x"}, files={"media": ("r.webm", b"abc", "video/webm")}
    )
    assert response.status_code == 404


def _token_for(session_id, expiry_seconds=60, secret=None, other_session=None):
    session = db.get_session(session_id)
    token, _ = generate_challenge_token(
        session_id=other_session or session_id,
        visual_challenge=session["visual_challenge"],
        verbal_challenge=session["verbal_challenge"],
        secret_key=secret or settings.SECRET_KEY,
        expiry_seconds=expiry_seconds,
    )
    return token


def test_a_bad_token_is_a_401_and_does_not_use_up_the_session():
    session_id = client.post("/api/v1/sessions").json()["session_id"]
    media = require(GENUINE_5WORD_NOFACE_VIDEO_WEBM)
    bad_tokens = {
        "expired": _token_for(session_id, expiry_seconds=-5),
        "wrong secret": _token_for(session_id, secret="another-secret-of-more-than-32-characters!"),
        "another session's token": _token_for(session_id, other_session="some-other-session"),
        "not a token": "garbage",
    }

    for name, token in bad_tokens.items():
        response = _submit(session_id, token, media)
        assert response.status_code == 401, name

    assert db.get_session(session_id)["status"] == VerificationStatus.CREATED.value


def test_a_second_submit_for_the_same_session_is_a_409(monkeypatch):
    """Not the claim race (tested above) but the plain case: the session was already submitted."""
    from app import orchestrator

    monkeypatch.setattr(orchestrator, "run_verification", lambda *args, **kwargs: None)  # no analysis needed here
    session_id = client.post("/api/v1/sessions").json()["session_id"]
    token = _token_for(session_id)
    media = require(GENUINE_5WORD_NOFACE_VIDEO_WEBM)

    assert _submit(session_id, token, media).status_code == 202
    second = _submit(session_id, token, media)

    assert second.status_code == 409 and "already been submitted" in second.json()["detail"]


def test_a_session_that_was_not_submitted_shows_created_and_no_signals():
    session_id = client.post("/api/v1/sessions").json()["session_id"]

    body = client.get(f"/api/v1/sessions/{session_id}").json()

    assert body["status"] == "CREATED" and body["confidence"] is None
    assert not body["signals"]


# --- a verified result travels through the API unchanged -----------------------------------------

def test_a_verified_verdict_is_stored_and_returned_and_the_upload_is_deleted(monkeypatch):
    """The analysis is replaced by a stub that verifies: this tests the plumbing, not the detectors."""
    from pathlib import Path

    from app import orchestrator
    from app.fusion import FusionResult
    from app.schemas.detector import DetectorResult

    def verified(media_path, visual_challenge, verbal_challenge, phases=None):
        signals = {
            "visual_challenge": DetectorResult(score=1.0, passed=True, reason="turned"),
            "audio_pipeline": DetectorResult(score=0.9, passed=True, reason="said", details={"match_count": 5, "insertions": 0}),
        }
        return orchestrator.AnalysisResult(
            signals=signals, fusion=FusionResult(VerificationStatus.VERIFIED, 0.91, "all checks agree"), phases=phases
        )

    monkeypatch.setattr(orchestrator, "analyze_media", verified)
    session_id = client.post("/api/v1/sessions").json()["session_id"]

    assert _submit(session_id, _token_for(session_id), require(GENUINE_5WORD_NOFACE_VIDEO_WEBM)).status_code == 202

    body = client.get(f"/api/v1/sessions/{session_id}").json()
    assert body["status"] == "VERIFIED" and body["confidence"] == 0.91
    assert body["signals"]["audio_pipeline"]["details"] == {"match_count": 5, "insertions": 0}
    assert list(Path(settings.UPLOAD_TEMP_DIR).glob("upload_*")) == []
