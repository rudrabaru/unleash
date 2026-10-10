"""
What is stored with a session: counts, codes and scores, not what the person said.
"""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import db
from app.core.config import settings
from app.core.security import generate_challenge_token
from app.main import app
from app.modules.audio._phrase_compliance import run_phrase_compliance
from app.schemas.detector import DetectorResult
from _paths import GENUINE_5WORD_PHRASE, OTHER_5WORD_PHRASE

SPOKEN = {"transcript": "walnut lantern", "words_detected": ["walnut"], "word_timestamps": [{"word": "walnut"}], "matched_pairs": ["walnut -> walnut"]}
COUNTS = {"match_count": 4, "insertions": 1, "phrase_matched": True, "speech_duration_seconds": 4.0}


def _store(details):
    now = datetime.now(timezone.utc)
    db.create_session("privacy", "PROCESSING", "LOOK_UP", GENUINE_5WORD_PHRASE, now)
    db.write_decision("privacy", "SUSPICIOUS", 0.7, "reason", {"audio_pipeline": DetectorResult(score=0.5, passed=True, reason="ok", details=details)}, now)
    return db.get_session("privacy")["signals"]["audio_pipeline"].details


def test_the_words_that_were_heard_are_not_stored_by_default():
    stored = _store({**SPOKEN, **COUNTS})

    assert stored == COUNTS


def test_they_can_be_kept_for_a_development_database(monkeypatch):
    monkeypatch.setattr(settings, "STORE_TRANSCRIPTS", True)

    stored = _store({**SPOKEN, **COUNTS})

    assert stored == {**SPOKEN, **COUNTS}


def test_a_phrase_result_explains_itself_without_quoting_the_speech(genuine_wav):
    right = run_phrase_compliance(genuine_wav, GENUINE_5WORD_PHRASE)
    wrong = run_phrase_compliance(genuine_wav, OTHER_5WORD_PHRASE)

    for result in (right, wrong):
        assert result.details["transcript"]  # the caller still has it in memory (the demo endpoint returns it)
        assert "Transcript" not in result.reason and "Matched pairs" not in result.reason
        challenge = set(result.details["target_words"])  # the challenge itself is public and may be named
        heard_but_not_asked = {w.strip(".,?! ").lower() for w in result.details["words_detected"]} - challenge
        assert heard_but_not_asked and not any(word in result.reason.lower() for word in heard_but_not_asked)


def test_a_finished_session_holds_no_speech_content(protocol_take):
    client = TestClient(app)
    session_id = client.post("/api/v1/sessions").json()["session_id"]
    with db._connect() as conn:
        conn.execute(
            "UPDATE sessions SET visual_challenge = ?, verbal_challenge = ? WHERE session_id = ?",
            ("TURN_HEAD_LEFT", GENUINE_5WORD_PHRASE, session_id),
        )
    token, _ = generate_challenge_token(
        session_id=session_id, visual_challenge="TURN_HEAD_LEFT", verbal_challenge=GENUINE_5WORD_PHRASE,
        secret_key=settings.SECRET_KEY, expiry_seconds=60,
    )
    with open(protocol_take, "rb") as f:
        assert client.post(
            f"/api/v1/sessions/{session_id}/submit", data={"token": token}, files={"media": ("r.webm", f, "video/webm")}
        ).status_code == 202

    body = client.get(f"/api/v1/sessions/{session_id}").json()

    audio = body["signals"]["audio_pipeline"]
    assert audio["details"]["match_count"] >= 4  # the counts are there
    assert not set(audio["details"]) & set(SPOKEN)
    assert "Transcript" not in audio["reason"] and "Transcript" not in body["decision_reason"]
