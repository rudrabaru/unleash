"""
Capture quality (app/quality.py): what is refused at the door, what is sent back as RETRY, and that a
person who did nothing wrong is never told they failed.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, orchestrator, quality
from app.core.config import settings
from app.core.security import generate_challenge_token
from app.main import app
from app.media.probe import MediaProbe, StreamTimes
from app.protocol import PROTOCOL_V1
from app.schemas.detector import DetectorResult
from app.schemas.session import VerificationStatus
from _paths import GENUINE_5WORD_NOFACE_VIDEO_WEBM, GENUINE_5WORD_PHRASE, OTHER_5WORD_PHRASE, require

client = TestClient(app, raise_server_exceptions=False)


def _probe(duration=13.2, width=1280, height=720, video_first=0.0, audio_first=0.0, over_limit=False, error=None):
    return MediaProbe(
        video=StreamTimes(video_first, video_first + duration),
        audio=StreamTimes(audio_first, audio_first + duration),
        width=width, height=height, over_limit=over_limit, error=error,
    )


# --- refused at the door ------------------------------------------------------------------------

def test_a_normal_recording_is_not_refused():
    assert quality.upload_rejection(_probe()) is None
    assert quality.upload_rejection(_probe(width=1920, height=1080)) is None
    assert quality.upload_rejection(_probe(width=1080, height=1920)) is None  # a phone held upright


@pytest.mark.parametrize("probe", [
    _probe(error="not a media file"), _probe(over_limit=True), _probe(width=2560, height=1440), _probe(width=1080, height=2561),
])
def test_an_unreadable_overlong_or_oversized_recording_is_refused(probe):
    assert quality.upload_rejection(probe)


def test_an_upload_that_arrives_before_it_could_have_been_made_is_refused():
    created = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)

    assert quality.submitted_too_early(created, created + timedelta(seconds=3), 12.0)
    assert quality.submitted_too_early(created, created + timedelta(seconds=13), 12.0) is None
    assert quality.submitted_too_early(created, created + timedelta(seconds=1), 0.0) is None  # switched off


# --- capture problems that need no detector ----------------------------------------------------

def test_a_recording_that_is_too_short_is_a_capture_problem_with_windows_only():
    short = _probe(duration=6.0)

    assert quality.recording_problem(short, PROTOCOL_V1).code == "too_short"
    assert quality.recording_problem(short, None) is None  # without windows any length is judged as before


def test_picture_and_sound_that_start_apart_are_a_capture_problem():
    assert quality.recording_problem(_probe(video_first=1.0), PROTOCOL_V1).code == "av_skew"
    assert quality.recording_problem(_probe(video_first=0.3), PROTOCOL_V1) is None


def test_a_well_formed_recording_has_no_capture_problem():
    assert quality.recording_problem(_probe(), PROTOCOL_V1) is None


# --- capture problems a detector finds ---------------------------------------------------------

def _signal(details):
    return DetectorResult(score=None, passed=False, reason="x", error=None, details=details)


@pytest.mark.parametrize("signals, code", [
    ({"visual_challenge": _signal({"failure_code": "bad_baseline"})}, "bad_baseline"),
    ({"visual_challenge": _signal({"failure_code": "no_face"})}, "no_face"),
    ({"audio_pipeline": _signal({"failure_code": "mic_silent"})}, "mic_silent"),
])
def test_missing_face_or_dead_microphone_is_a_capture_problem(signals, code):
    assert quality.capture_problem_in(signals).code == code


@pytest.mark.parametrize("failure_code", ["no_motion", "wrong_direction", "no_hold", "no_return", None])
def test_a_missed_action_is_not_a_capture_problem(failure_code):
    assert quality.capture_problem_in({"visual_challenge": _signal({"failure_code": failure_code})}) is None


# --- the analysis sends an unjudgeable recording back without running a detector ---------------

def test_a_short_recording_is_sent_back_before_any_detector_runs():
    analysis = orchestrator.analyze_media(
        require(GENUINE_5WORD_NOFACE_VIDEO_WEBM), "TURN_HEAD_LEFT", GENUINE_5WORD_PHRASE, phases=PROTOCOL_V1
    )

    assert analysis.fusion.status == VerificationStatus.RETRY and analysis.fusion.confidence is None
    assert set(analysis.signals) == {"recording"}
    assert analysis.signals["recording"].details["failure_code"] == "too_short"
    assert "frames" not in analysis.timings and "audio" not in analysis.timings


# --- through the sessions API --------------------------------------------------------------------

def _session(visual="TURN_HEAD_LEFT", phrase=GENUINE_5WORD_PHRASE):
    session_id = client.post("/api/v1/sessions").json()["session_id"]
    with db._connect() as conn:
        conn.execute(
            "UPDATE sessions SET visual_challenge = ?, verbal_challenge = ? WHERE session_id = ?", (visual, phrase, session_id)
        )
    token, _ = generate_challenge_token(
        session_id=session_id, visual_challenge=visual, verbal_challenge=phrase,
        secret_key=settings.SECRET_KEY, expiry_seconds=60,
    )
    return session_id, token


def _submit(session_id, token, path):
    with open(path, "rb") as f:
        return client.post(
            f"/api/v1/sessions/{session_id}/submit", data={"token": token}, files={"media": ("recording.webm", f, "video/webm")}
        )


def _result(session_id):
    return client.get(f"/api/v1/sessions/{session_id}").json()


@pytest.mark.parametrize("fixture", ["oversized_picture_webm", "long_recording_webm", "garbage_webm"])
def test_an_unusable_upload_is_refused_and_the_session_stays_usable(fixture, request):
    media = request.getfixturevalue(fixture)
    session_id, token = _session()

    response = _submit(session_id, token, media)

    assert response.status_code == 422
    assert db.get_session(session_id)["status"] == VerificationStatus.CREATED.value
    assert list(Path(settings.UPLOAD_TEMP_DIR).glob("upload_*")) == []  # the refused file is not kept


def test_an_upload_sooner_than_the_recording_could_be_made_is_refused_then_accepted_later(monkeypatch, protocol_take):
    monkeypatch.setattr(settings, "MIN_SUBMIT_SECONDS", 12.0)
    session_id, token = _session()

    too_soon = _submit(session_id, token, protocol_take)

    assert too_soon.status_code == 422 and "before it could have been made" in too_soon.json()["detail"]
    assert db.get_session(session_id)["status"] == VerificationStatus.CREATED.value
    long_ago = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    with db._connect() as conn:
        conn.execute("UPDATE sessions SET created_at = ? WHERE session_id = ?", (long_ago, session_id))
    assert _submit(session_id, token, protocol_take).status_code == 202


def test_a_short_recording_gets_retry_not_failed():
    session_id, token = _session()

    assert _submit(session_id, token, require(GENUINE_5WORD_NOFACE_VIDEO_WEBM)).status_code == 202

    result = _result(session_id)
    assert result["status"] == "RETRY" and result["confidence"] is None
    assert "needs about 13 s" in result["decision_reason"]
    assert result["signals"]["recording"]["details"]["failure_code"] == "too_short"


def test_a_dead_microphone_gets_retry(protocol_take_with_silent_microphone):
    session_id, token = _session()

    assert _submit(session_id, token, protocol_take_with_silent_microphone).status_code == 202

    result = _result(session_id)
    assert result["status"] == "RETRY", result["decision_reason"]
    assert result["signals"]["audio_pipeline"]["details"]["failure_code"] == "mic_silent"


def test_nobody_in_front_of_the_camera_gets_retry(protocol_take_without_a_face):
    session_id, token = _session()

    assert _submit(session_id, token, protocol_take_without_a_face).status_code == 202

    result = _result(session_id)
    assert result["status"] == "RETRY", result["decision_reason"]
    assert result["signals"]["visual_challenge"]["details"]["failure_code"] == "bad_baseline"


def test_a_picture_that_starts_a_second_after_the_sound_gets_retry(protocol_take_with_late_picture):
    session_id, token = _session()

    assert _submit(session_id, token, protocol_take_with_late_picture).status_code == 202

    result = _result(session_id)
    assert result["status"] == "RETRY"
    assert result["signals"]["recording"]["details"]["failure_code"] == "av_skew"


def test_the_wrong_words_are_still_a_failure_not_a_retry(protocol_take):
    """A readable recording of a real face and a real voice that says something else is evidence, not a capture problem."""
    session_id, token = _session(phrase=OTHER_5WORD_PHRASE)

    assert _submit(session_id, token, protocol_take).status_code == 202

    result = _result(session_id)
    assert result["status"] == "FAILED"
    assert result["signals"]["audio_pipeline"]["passed"] is False


def test_an_error_on_our_side_asks_for_a_retry_and_says_so(monkeypatch, protocol_take):
    def explode(*args, **kwargs):
        raise RuntimeError("model crashed")

    monkeypatch.setattr(orchestrator, "analyze_media", explode)
    session_id, token = _session()

    _submit(session_id, token, protocol_take)  # the background error is raised and logged, not hidden

    result = _result(session_id)
    assert result["status"] == "RETRY"
    assert "error on our side" in result["decision_reason"]
