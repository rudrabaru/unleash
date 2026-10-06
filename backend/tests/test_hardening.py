"""Backend hardening: weak-secret refusal, upload size limit, sessions left in PROCESSING."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import db
from app.core.config import Settings, settings
from app.core.security import generate_challenge_token
from app.main import app
from app.schemas.session import VerificationStatus

client = TestClient(app)


def test_default_secret_is_allowed_in_development_only():
    Settings(_env_file=None, ENVIRONMENT="development")
    with pytest.raises(ValueError):
        Settings(_env_file=None, ENVIRONMENT="production")


def test_short_secret_is_refused_outside_development():
    with pytest.raises(ValueError):
        Settings(_env_file=None, ENVIRONMENT="production", SECRET_KEY="too-short")
    Settings(_env_file=None, ENVIRONMENT="production", SECRET_KEY="k" * 40)


def _new_session_and_token():
    session_id = client.post("/api/v1/sessions").json()["session_id"]
    session = db.get_session(session_id)
    token, _ = generate_challenge_token(
        session_id=session_id,
        visual_challenge=session["visual_challenge"],
        verbal_challenge=session["verbal_challenge"],
        secret_key=settings.SECRET_KEY,
        expiry_seconds=60,
    )
    return session_id, token


def test_oversized_upload_is_refused_and_the_session_stays_usable(monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 1024)
    session_id, token = _new_session_and_token()
    response = client.post(
        f"/api/v1/sessions/{session_id}/submit",
        data={"token": token},
        files={"media": ("big.webm", b"\0" * 4096, "video/webm")},
    )
    assert response.status_code == 413
    assert db.get_session(session_id)["status"] == VerificationStatus.CREATED.value


def test_sessions_left_processing_are_closed_at_startup():
    stuck, _ = _new_session_and_token()
    fresh, _ = _new_session_and_token()
    assert db.claim_for_processing(stuck, datetime.now(timezone.utc))

    assert db.fail_orphaned_sessions(datetime.now(timezone.utc)) == 1

    assert db.get_session(stuck)["status"] == VerificationStatus.FAILED.value
    assert "interrupted" in db.get_session(stuck)["decision_reason"]
    assert db.get_session(fresh)["status"] == VerificationStatus.CREATED.value


def test_deepfake_settings_are_read_through_settings(monkeypatch):
    monkeypatch.setenv("UNLEASH_FAKE_THRESHOLD", "0.7")
    monkeypatch.setenv("UNLEASH_XCEPTION_CHECKPOINT", "C:/models/x.pth")
    loaded = Settings(_env_file=None)
    assert loaded.FAKE_THRESHOLD == 0.7 and loaded.XCEPTION_CHECKPOINT == "C:/models/x.pth"


def test_a_malformed_deepfake_setting_stops_startup_instead_of_being_ignored(monkeypatch):
    monkeypatch.setenv("UNLEASH_FAKE_THRESHOLD", "high")
    with pytest.raises(ValueError):
        Settings(_env_file=None)
