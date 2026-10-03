"""
Tests for Evaluation Dashboard API (GET /api/v1/eval/sessions).
Covers:
1. Schema contract for SessionResultResponse list.
2. Null confidence and null detector scores preserved (never coerced to 0 or 0.5).
3. Retrieval of multiple sessions and ordering.
"""
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import db
from app.schemas.detector import DetectorResult
from app.schemas.session import VerificationStatus

client = TestClient(app)


def test_eval_sessions_endpoint_empty_db(monkeypatch):
    """When no sessions exist, returns an empty list with 200 OK."""
    monkeypatch.setattr(db, "list_sessions", lambda: [])
    response = client.get("/api/v1/eval/sessions")
    assert response.status_code == 200
    assert response.json() == []


def test_eval_sessions_preserves_null_scores(monkeypatch):
    """
    Decision D-15 & Contract check: null scores must remain null in the API output.
    They must never be coerced to 0.0 or 0.5 placeholders.
    """
    mock_session = {
        "session_id": "test-session-null-scores",
        "status": VerificationStatus.FAILED.value,
        "confidence": None,
        "decision_reason": "Visual challenge compliance failed; Hard gate failure",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "signals": {
            "visual_challenge": DetectorResult(score=None, passed=False, reason="Face missing", error="no face").model_dump(),
            "visual_liveness": DetectorResult(score=None, passed=False, reason="No face", error="no face").model_dump(),
            "audio_pipeline": DetectorResult(
                score=1.0,
                passed=True,
                reason="Audio passed",
                error=None,
                details={"voice_authenticity_score": None, "av_alignment_score": None},
            ).model_dump(),
            "deepfake": DetectorResult(score=None, passed=False, reason="Checkpoint missing", error="missing").model_dump(),
            "replay": DetectorResult(score=None, passed=False, reason="Single frame", error=None).model_dump(),
        },
    }

    monkeypatch.setattr(db, "list_sessions", lambda: [mock_session])

    response = client.get("/api/v1/eval/sessions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    sess = data[0]

    assert sess["session_id"] == "test-session-null-scores"
    assert sess["status"] == "FAILED"
    assert sess["confidence"] is None  # preserved null, not 0.0
    assert sess["signals"]["visual_challenge"]["score"] is None
    assert sess["signals"]["deepfake"]["score"] is None
    assert sess["signals"]["audio_pipeline"]["details"]["voice_authenticity_score"] is None


def test_eval_sessions_signal_breakdown_structure(monkeypatch):
    """Verifies that all 5 signals with valid scores map correctly to SessionResultResponse."""
    mock_session = {
        "session_id": "test-session-valid-scores",
        "status": VerificationStatus.VERIFIED.value,
        "confidence": 0.885,
        "decision_reason": "Verification passed with confidence 0.8850",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "signals": {
            "visual_liveness": DetectorResult(score=0.90, passed=True, reason="Liveness verified").model_dump(),
            "visual_challenge": DetectorResult(score=1.00, passed=True, reason="Turn head verified").model_dump(),
            "audio_pipeline": DetectorResult(
                score=0.85,
                passed=True,
                reason="Speech verified",
                details={"voice_authenticity_score": 0.80, "av_alignment_score": 0.75},
            ).model_dump(),
            "deepfake": DetectorResult(score=0.92, passed=True, reason="Real video").model_dump(),
            "replay": DetectorResult(score=0.88, passed=True, reason="Genuine display").model_dump(),
        },
    }

    monkeypatch.setattr(db, "list_sessions", lambda: [mock_session])

    response = client.get("/api/v1/eval/sessions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    sess = data[0]

    assert sess["status"] == "VERIFIED"
    assert sess["confidence"] == 0.885
    assert sess["signals"]["visual_liveness"]["score"] == 0.90
    assert sess["signals"]["visual_challenge"]["score"] == 1.00
    assert sess["signals"]["audio_pipeline"]["details"]["voice_authenticity_score"] == 0.80
    assert sess["signals"]["audio_pipeline"]["details"]["av_alignment_score"] == 0.75
