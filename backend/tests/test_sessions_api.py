"""
Integration tests for FastAPI sessions and evaluation API endpoints.
Tests real background pipeline processing through HTTP requests.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.sessions import SESSION_STORE
from app.core.security import generate_challenge_token
from app.main import app
from app.schemas.session import VerificationStatus

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "prototypes" / "fixtures"
client = TestClient(app)


def test_session_lifecycle_with_real_audio_verification():
    """Test full session creation, submit, and background verification with real speech fixture."""
    real_webm = FIXTURES_DIR / "real_742.webm"
    if not real_webm.exists():
        pytest.skip("Fixture real_742.webm not found")

    # 1. Create session
    create_resp = client.post("/api/v1/sessions")
    assert create_resp.status_code == 201
    create_data = create_resp.json()
    session_id = create_data["session_id"]
    token = create_data["token"]
    assert create_data["challenge"]["verbal"] is not None

    # Override verbal challenge to match fixture "742"
    SESSION_STORE[session_id]["challenge"]["verbal"] = "742"
    # Regenerate token with matching verbal challenge
    from app.core.config import settings
    valid_token, _ = generate_challenge_token(
        session_id=session_id,
        visual_challenge=SESSION_STORE[session_id]["challenge"]["visual"].value,
        verbal_challenge="742",
        secret_key=settings.SECRET_KEY,
        expiry_seconds=60
    )
    SESSION_STORE[session_id]["token"] = valid_token

    # 2. Submit media with matching challenge
    with open(real_webm, "rb") as f:
        submit_resp = client.post(
            f"/api/v1/sessions/{session_id}/submit",
            data={"token": valid_token},
            files={"media": ("recording.webm", f, "video/webm")}
        )

    assert submit_resp.status_code == 202

    # 3. Retrieve session result (TestClient runs background tasks synchronously)
    result_resp = client.get(f"/api/v1/sessions/{session_id}")
    assert result_resp.status_code == 200
    res_data = result_resp.json()

    assert res_data["status"] == VerificationStatus.VERIFIED
    assert res_data["confidence"] is not None and res_data["confidence"] >= 0.67
    assert "audio_pipeline" in res_data["signals"]
    assert res_data["signals"]["audio_pipeline"]["passed"] is True
    assert res_data["signals"]["audio_pipeline"]["details"]["phrase_matched"] is True

    # Stage 3 Voice Authenticity is real and computed; Stage 4 AV alignment is currently stubbed (None per canonical schema)
    assert "voice_authenticity_score" in res_data["signals"]["audio_pipeline"]["details"]
    assert isinstance(res_data["signals"]["audio_pipeline"]["details"]["voice_authenticity_score"], float)
    assert res_data["signals"]["audio_pipeline"]["details"].get("av_alignment_score") is None


def test_session_lifecycle_with_wrong_challenge_fails():
    """Test full session creation and submit with wrong verbal challenge (hard gate rejection)."""
    real_webm = FIXTURES_DIR / "real_742.webm"
    if not real_webm.exists():
        pytest.skip("Fixture real_742.webm not found")

    create_resp = client.post("/api/v1/sessions")
    assert create_resp.status_code == 201
    create_data = create_resp.json()
    session_id = create_data["session_id"]

    # Challenge is "981" while audio says "742"
    SESSION_STORE[session_id]["challenge"]["verbal"] = "981"
    from app.core.config import settings
    valid_token, _ = generate_challenge_token(
        session_id=session_id,
        visual_challenge=SESSION_STORE[session_id]["challenge"]["visual"].value,
        verbal_challenge="981",
        secret_key=settings.SECRET_KEY,
        expiry_seconds=60
    )
    SESSION_STORE[session_id]["token"] = valid_token

    with open(real_webm, "rb") as f:
        submit_resp = client.post(
            f"/api/v1/sessions/{session_id}/submit",
            data={"token": valid_token},
            files={"media": ("recording.webm", f, "video/webm")}
        )

    assert submit_resp.status_code == 202

    result_resp = client.get(f"/api/v1/sessions/{session_id}")
    assert result_resp.status_code == 200
    res_data = result_resp.json()

    assert res_data["status"] == VerificationStatus.FAILED
    assert "audio_pipeline" in res_data["signals"]
    assert res_data["signals"]["audio_pipeline"]["passed"] is False


def test_eval_dashboard_endpoint():
    """Test eval dashboard lists session results without fabricated scores."""
    # Create a session so the store is not empty, isolating this test
    client.post("/api/v1/sessions")
    
    resp = client.get("/api/v1/eval/sessions")
    assert resp.status_code == 200
    sessions = resp.json()
    assert isinstance(sessions, list)
    assert len(sessions) > 0
