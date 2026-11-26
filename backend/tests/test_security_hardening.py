"""
The hardening package (D-56): uploads are opened only as Matroska/WebM or MP4 from local files; a client
is rate-limited; old sessions are deleted; a caller never sees internal error text; analyses run on one
worker behind a bounded queue; start-up work runs in the lifespan, not at import; CORS allows no more
than the browser needs.
"""
import importlib
import shutil
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import av
import pytest
from fastapi.testclient import TestClient

from app import db, fusion, housekeeping, orchestrator
from app.analysis_queue import AnalysisQueue
from app.api.v1.endpoints import sessions
from app.core import rate_limit
from app.core.config import settings
from app.core.security import generate_challenge_token
from app.main import app
from app.media.frames import load_frames
from app.media.probe import probe_streams
from app.modules.audio._extraction import extract_wav, probe_media
from app.schemas.detector import DetectorResult
from _paths import GENUINE_5WORD_NOFACE_VIDEO_WEBM, require

client = TestClient(app)


# --- 1. uploads are opened only as the formats a recording can be ----------------------------------

@pytest.fixture(scope="module")
def wav_named_webm(tmp_path_factory):
    """A valid audio file of a format no recording comes in (WAV), saved under an upload's name."""
    folder = tmp_path_factory.mktemp("disguised")
    wav = folder / "tone.wav"
    subprocess.run(
        [shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "sine=frequency=440:sample_rate=16000", "-t", "2", str(wav)],
        check=True,
    )
    disguised = folder / "upload_abc.webm"
    disguised.write_bytes(wav.read_bytes())
    return disguised


def test_without_the_allow_list_ffmpeg_would_open_the_disguised_file(wav_named_webm):
    """The control: format guessing alone accepts it, so the refusals below come from the allow-list."""
    with av.open(str(wav_named_webm)) as container:
        assert container.format.name == "wav"


def test_every_reader_refuses_a_container_a_recording_cannot_be(wav_named_webm, tmp_path):
    assert probe_streams(wav_named_webm).error is not None
    assert load_frames(wav_named_webm).error is not None
    assert probe_media(wav_named_webm)["ok"] is False
    ok, error, _ = extract_wav(wav_named_webm, tmp_path / "out.wav")
    assert ok is False and error


def test_real_recordings_in_both_allowed_families_still_open():
    webm = require(GENUINE_5WORD_NOFACE_VIDEO_WEBM)
    assert probe_streams(webm).error is None
    assert probe_media(webm)["ok"] is True


# --- 2. rate limit and retention ------------------------------------------------------------------

def test_the_limiter_allows_the_limit_then_says_how_long_to_wait():
    limiter = rate_limit.SlidingWindowLimiter(lambda: 2, window_seconds=60)
    assert limiter.retry_after("a", now=0.0) is None
    assert limiter.retry_after("a", now=1.0) is None
    assert limiter.retry_after("a", now=2.0) == pytest.approx(58.0)
    assert limiter.retry_after("b", now=2.0) is None  # another client has its own allowance
    assert limiter.retry_after("a", now=60.5) is None  # the first call has left the window


def test_a_limit_of_zero_turns_the_limiter_off():
    limiter = rate_limit.SlidingWindowLimiter(lambda: 0)
    assert all(limiter.retry_after("a") is None for _ in range(100))


def test_too_many_sessions_from_one_client_get_429_with_retry_after(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 2)
    rate_limit.session_limiter.reset()
    try:
        codes = [client.post("/api/v1/sessions").status_code for _ in range(2)]
        third = client.post("/api/v1/sessions")
    finally:
        rate_limit.session_limiter.reset()
    assert codes == [201, 201]
    assert third.status_code == 429 and int(third.headers["Retry-After"]) >= 1


def test_the_forwarded_address_counts_only_behind_a_trusted_proxy(monkeypatch):
    class FakeRequest:
        headers = {"x-forwarded-for": "203.0.113.7, 10.0.0.1"}
        client = type("Client", (), {"host": "127.0.0.1"})()

    assert rate_limit.client_key(FakeRequest()) == "127.0.0.1"
    monkeypatch.setattr(settings, "TRUST_FORWARDED_FOR", True)
    assert rate_limit.client_key(FakeRequest()) == "203.0.113.7"


def test_sessions_past_retention_are_deleted_with_their_scores(monkeypatch):
    monkeypatch.setattr(settings, "SESSION_RETENTION_HOURS", 24.0)
    now = datetime.now(timezone.utc)
    old = now - timedelta(hours=30)
    db.create_session("old", "CREATED", "LOOK_UP", "a b c d e", old)
    db.write_decision("old", "FAILED", None, "r", {"replay": DetectorResult(score=0.3, passed=False, reason="r")}, old)
    db.create_session("old-running", "CREATED", "LOOK_UP", "a b c d e", old)
    db.claim_for_processing("old-running", old)
    db.create_session("recent", "CREATED", "LOOK_UP", "a b c d e", now)

    assert housekeeping.prune_old_sessions(now, force=True) == 1

    assert db.get_session("old") is None
    with db._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM signal_scores WHERE session_id = 'old'").fetchone()[0] == 0
    assert db.get_session("old-running") is not None  # never pulled from under a running analysis
    assert db.get_session("recent") is not None


def test_a_retention_of_zero_keeps_everything(monkeypatch):
    monkeypatch.setattr(settings, "SESSION_RETENTION_HOURS", 0.0)
    now = datetime.now(timezone.utc)
    db.create_session("ancient", "CREATED", "LOOK_UP", "a b c d e", now - timedelta(days=400))
    assert housekeeping.prune_old_sessions(now, force=True) == 0
    assert db.get_session("ancient") is not None


# --- 3. a caller never sees internal error text ---------------------------------------------------

SECRET_PATH = r"C:\srv\unleash\temp_uploads\upload_123.webm"


def test_a_result_hides_internal_errors_but_the_database_keeps_them():
    now = datetime.now(timezone.utc)
    db.create_session("s-err", "CREATED", "LOOK_UP", "a b c d e", now)
    signals = {
        "audio_pipeline": DetectorResult(
            score=None, passed=False, reason=f"Media file does not exist: {SECRET_PATH}", error="Media file not found",
            details={"speech_detected": False, "voice_check_error": f"OSError {SECRET_PATH}"},
        ),
        "replay": DetectorResult(score=0.4, passed=False, reason="Replay score below the line.", details={"lip_sync_error": "x", "moire": 0.1}),
    }
    db.write_decision("s-err", "FAILED", None, "Audio must-pass check failed.", signals, now)

    body = client.get("/api/v1/sessions/s-err").json()

    audio = body["signals"]["audio_pipeline"]
    assert audio["error"] == audio["reason"] == sessions.PUBLIC_CHECK_ERROR
    assert audio["details"] == {"speech_detected": False}
    assert body["signals"]["replay"]["reason"] == "Replay score below the line."  # an ordinary result is untouched
    assert body["signals"]["replay"]["details"] == {"moire": 0.1}
    assert SECRET_PATH not in str(body)
    assert db.get_session("s-err")["signals"]["audio_pipeline"].error == "Media file not found"


def test_the_verdict_does_not_quote_an_internal_error():
    signals = {
        "visual_challenge": DetectorResult(score=1.0, passed=True, reason="ok"),
        "audio_pipeline": DetectorResult(score=None, passed=False, reason=f"Failed to probe {SECRET_PATH}", error="probe"),
    }
    result = fusion.evaluate(signals)
    assert result.status.value == "FAILED" and SECRET_PATH not in result.reason


def test_a_bad_token_is_refused_without_saying_why():
    session_id = client.post("/api/v1/sessions").json()["session_id"]
    session = db.get_session(session_id)
    expired, _ = generate_challenge_token(
        session_id, session["visual_challenge"], session["verbal_challenge"], settings.SECRET_KEY, expiry_seconds=-5
    )
    with open(require(GENUINE_5WORD_NOFACE_VIDEO_WEBM), "rb") as f:
        response = client.post(
            f"/api/v1/sessions/{session_id}/submit", data={"token": expired}, files={"media": ("r.webm", f, "video/webm")}
        )
    assert response.status_code == 401
    assert "expired at" not in response.json()["detail"] and "HMAC" not in response.json()["detail"]


# --- 4. one worker behind a bounded queue ---------------------------------------------------------

def test_the_worker_runs_jobs_in_order_and_refuses_when_full():
    queue = AnalysisQueue()
    queue.start(capacity=1)
    try:
        gate, done, order = threading.Event(), threading.Event(), []
        assert queue.reserve()
        queue.submit(lambda: (gate.wait(5), order.append("first")))
        assert queue.reserve() is False  # the only place is taken by the running job

        gate.set()
        assert _wait_until(queue.reserve)  # the place comes back once the first job has finished
        assert order == ["first"]
        queue.submit(lambda: (order.append("second"), done.set()))
        assert done.wait(5) and order == ["first", "second"]
    finally:
        queue.stop()


def test_a_failing_job_does_not_stop_the_worker():
    queue = AnalysisQueue()
    queue.start(capacity=2)
    try:
        done = threading.Event()
        assert queue.reserve()
        queue.submit(lambda: 1 / 0)
        assert queue.reserve()
        queue.submit(done.set)
        assert done.wait(5)
    finally:
        queue.stop()


def test_a_queue_without_a_running_worker_takes_nothing():
    assert AnalysisQueue().reserve() is False


def test_a_full_queue_refuses_the_upload_and_leaves_the_session_usable(monkeypatch):
    monkeypatch.setattr(sessions.analysis_queue, "reserve", lambda: False)
    session_id = client.post("/api/v1/sessions").json()["session_id"]
    session = db.get_session(session_id)
    token, _ = generate_challenge_token(session_id, session["visual_challenge"], session["verbal_challenge"], settings.SECRET_KEY)

    with open(require(GENUINE_5WORD_NOFACE_VIDEO_WEBM), "rb") as f:
        response = client.post(
            f"/api/v1/sessions/{session_id}/submit", data={"token": token}, files={"media": ("r.webm", f, "video/webm")}
        )

    assert response.status_code == 503 and response.headers["Retry-After"]
    assert db.get_session(session_id)["status"] == "CREATED"
    assert not list(Path(settings.UPLOAD_TEMP_DIR).glob("upload_*"))  # the stored upload was removed again


def _wait_until(condition, seconds: float = 5.0) -> bool:
    deadline = threading.Event()
    for _ in range(int(seconds * 100)):
        if condition():
            return True
        deadline.wait(0.01)
    return condition()


# --- 5. start-up work belongs to the lifespan -----------------------------------------------------

def test_importing_the_app_does_no_start_up_work(monkeypatch):
    def refuse():
        raise AssertionError("start-up work ran at import")

    monkeypatch.setattr(housekeeping, "startup", refuse)
    import app.main

    importlib.reload(app.main)  # would raise if the module still did its start-up work at import


def test_the_lifespan_does_the_start_up_work_and_starts_the_worker(monkeypatch):
    calls = []
    monkeypatch.setattr(housekeeping, "startup", lambda: calls.append("startup"))
    monkeypatch.setattr(orchestrator, "warm_up", lambda: calls.append("warm_up"))
    started = []
    monkeypatch.setattr(sessions.analysis_queue, "start", lambda capacity: started.append(capacity))
    monkeypatch.setattr(sessions.analysis_queue, "stop", lambda: started.append("stopped"))

    with TestClient(app) as running:
        assert running.get("/health").status_code == 200

    assert calls == ["startup", "warm_up"]
    assert started == [settings.MAX_QUEUED_ANALYSES, "stopped"]


# --- 6. CORS allows what the browser needs and nothing more ---------------------------------------

def _preflight(method: str):
    return client.options(
        "/api/v1/sessions",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": method},
    )


def test_cors_allows_get_and_post_without_credentials():
    allowed = _preflight("POST")
    assert allowed.status_code == 200
    assert "access-control-allow-credentials" not in allowed.headers
    assert set(allowed.headers["access-control-allow-methods"].replace(" ", "").split(",")) == {"GET", "POST"}
    assert _preflight("DELETE").status_code == 400
