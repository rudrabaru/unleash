"""
The challenge protocol (app/protocol.py): the phase windows, how a session announces them, and the
hand-off to the analysis.
"""
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, orchestrator
from app.fusion import FusionResult
from app.main import app
from app.protocol import PROTOCOL_V1, WINDOW_GUARD_SECONDS
from app.schemas.session import ProtocolPayload, VerificationStatus

client = TestClient(app)


def test_phases_follow_each_other_without_gaps_from_zero_to_the_total():
    phases = PROTOCOL_V1.phases
    assert [p.name for p in phases] == ["read", "speak", "act"]
    assert phases[0].start == 0.0
    for earlier, later in zip(phases, phases[1:]):
        assert earlier.end == later.start
    assert PROTOCOL_V1.total_seconds == phases[-1].end == 13.0


def test_recording_length_bounds_surround_the_total():
    assert PROTOCOL_V1.min_recording_seconds < PROTOCOL_V1.total_seconds < PROTOCOL_V1.max_recording_seconds


def test_window_is_the_phase_widened_on_both_sides_and_never_negative():
    assert PROTOCOL_V1.window("speak") == (3.0, 8.0)
    assert PROTOCOL_V1.window("speak", before=0.4, after=0.7) == pytest.approx((2.6, 8.7))
    assert PROTOCOL_V1.window("read", before=WINDOW_GUARD_SECONDS) == (0.0, 3.0)


def test_phase_at_names_the_phase_a_moment_falls_in():
    assert PROTOCOL_V1.phase_at(0.0) == "read"
    assert PROTOCOL_V1.phase_at(2.99) == "read"
    assert PROTOCOL_V1.phase_at(3.0) == "speak"
    assert PROTOCOL_V1.phase_at(8.0) == "act"
    assert PROTOCOL_V1.phase_at(13.0) is None
    assert PROTOCOL_V1.phase_at(-0.1) is None


def test_an_unknown_phase_is_an_error_not_an_empty_window():
    with pytest.raises(KeyError):
        PROTOCOL_V1.window("listen")


def test_a_new_session_announces_the_windows_the_detectors_will_use():
    response = client.post("/api/v1/sessions")

    assert response.status_code == 201
    announced = ProtocolPayload(**response.json()["protocol"])
    assert announced == ProtocolPayload.from_windows(PROTOCOL_V1)
    assert [(p.name, p.start, p.end) for p in announced.phases] == [(p.name, p.start, p.end) for p in PROTOCOL_V1.phases]
    assert announced.total_seconds == PROTOCOL_V1.total_seconds


def test_the_session_flow_hands_the_protocol_to_the_analysis(monkeypatch, tmp_path):
    """run_verification is what a submitted session runs; it must give the analysis the windows."""
    seen = {}

    def fake_analyze(media_path, visual_challenge, verbal_challenge, phases=None):
        seen["phases"] = phases
        return orchestrator.AnalysisResult(
            signals={},
            fusion=FusionResult(status=VerificationStatus.FAILED, confidence=None, reason="stub"),
            phases=phases,
        )

    monkeypatch.setattr(orchestrator, "analyze_media", fake_analyze)
    now = datetime.now(timezone.utc)
    db.create_session("protocol-session", "PROCESSING", "TURN_HEAD_LEFT", "one two three four five", now)

    orchestrator.run_verification("protocol-session", Path(tmp_path / "unused.webm"), "TURN_HEAD_LEFT", "one two three four five")

    assert seen["phases"] is PROTOCOL_V1
    assert db.get_session("protocol-session")["status"] == "FAILED"


def test_analysis_without_windows_judges_the_whole_recording_as_before(monkeypatch):
    """phases=None is the default: it is what /verify and every pre-protocol clip use."""
    captured = {}

    def fake_inner(media_path, visual_challenge, verbal_challenge, phases):
        captured["phases"] = phases
        return "analysis"

    monkeypatch.setattr(orchestrator, "_analyze", fake_inner)

    assert orchestrator.analyze_media(Path("a.webm"), "LOOK_UP", "one two three four five") == "analysis"
    assert captured["phases"] is None


def test_phase_windows_are_immutable():
    with pytest.raises(AttributeError):  # dataclasses.FrozenInstanceError
        PROTOCOL_V1.phases[0].end = 99.0  # type: ignore[misc]
