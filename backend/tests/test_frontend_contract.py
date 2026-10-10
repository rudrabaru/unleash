"""The recorder page's TypeScript types must name exactly the fields the API returns, and a stored
decision must come back unchanged from the database."""
import re
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.protocol import PROTOCOL_V1
from app.schemas.detector import DetectorResult
from app.schemas.session import (
    PhaseWindow,
    ProtocolPayload,
    SessionCreateResponse,
    SessionResultResponse,
    VisualChallengeType,
)

TYPES_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "app" / "types.ts"


def _ts_interface_fields(name: str) -> set:
    source = TYPES_TS.read_text(encoding="utf-8")
    body = re.search(r"export interface %s \{(.*?)\n\}" % name, source, re.S).group(1)
    # top-level members only: lines indented by exactly two spaces
    return set(re.findall(r"^  (\w+)\??:", body, re.M))


def test_session_result_fields_match_the_typescript_type():
    assert _ts_interface_fields("SessionResult") == set(SessionResultResponse.model_fields)


def test_session_challenge_fields_match_the_typescript_type():
    assert _ts_interface_fields("SessionChallenge") == set(SessionCreateResponse.model_fields)


def test_protocol_fields_match_the_typescript_types():
    assert _ts_interface_fields("Protocol") == set(ProtocolPayload.model_fields)
    assert _ts_interface_fields("PhaseWindow") == set(PhaseWindow.model_fields)


def test_phase_names_match_the_typescript_type():
    source = TYPES_TS.read_text(encoding="utf-8")
    declared = set(re.findall(r'"(\w+)"', re.search(r"type PhaseName =(.*?);", source, re.S).group(1)))
    assert declared == {phase.name for phase in PROTOCOL_V1.phases}


def test_detector_result_fields_match_the_typescript_type():
    assert _ts_interface_fields("DetectorResult") == set(DetectorResult.model_fields)


def test_visual_challenge_values_match_the_typescript_type():
    source = TYPES_TS.read_text(encoding="utf-8")
    declared = set(re.findall(r'"(\w+)"', re.search(r"type VisualChallenge =(.*?);", source, re.S).group(1)))
    assert declared == {c.value for c in VisualChallengeType}


def test_a_decision_round_trips_through_the_database():
    now = datetime.now(timezone.utc)
    db.create_session("s1", "CREATED", "LOOK_UP", "one two three four five", now)
    signals = {
        "audio_pipeline": DetectorResult(score=0.6, passed=True, reason="ok", details={"match_count": 4}),
        "deepfake": DetectorResult(score=None, passed=False, reason="no model", error="checkpoint missing"),
    }
    db.write_decision("s1", "SUSPICIOUS", 0.67, "reason text", signals, now)

    stored = db.get_session("s1")
    assert stored["status"] == "SUSPICIOUS" and stored["confidence"] == 0.67
    response = SessionResultResponse(**stored)
    assert response.signals["audio_pipeline"].details == {"match_count": 4}
    assert response.signals["deepfake"].score is None and response.signals["deepfake"].error == "checkpoint missing"
