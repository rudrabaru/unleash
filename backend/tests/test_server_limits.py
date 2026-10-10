"""
Server limits and start-up behaviour: safe defaults, anchored paths, a request body that is refused
while it arrives, the readiness endpoint, the demo endpoint's limits, and the start-up sweep.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import housekeeping, orchestrator
from app.core.config import Settings, settings
from app.main import app

client = TestClient(app)
BACKEND_DIR = Path(__file__).resolve().parents[1]


# --- defaults and paths --------------------------------------------------------------------------

def test_the_defaults_are_the_safe_ones_for_a_server():
    assert Settings.model_fields["ENVIRONMENT"].default == "production"
    assert Settings.model_fields["DEBUG"].default is False


def test_relative_paths_are_anchored_to_the_backend_folder_whatever_the_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    loaded = Settings(_env_file=None, ENVIRONMENT="development", UPLOAD_TEMP_DIR="./uploads", DATABASE_URL="sqlite:///./app.db")

    assert Path(loaded.UPLOAD_TEMP_DIR) == (BACKEND_DIR / "uploads").resolve()
    assert loaded.DATABASE_URL == "sqlite:///" + (BACKEND_DIR / "app.db").resolve().as_posix()


def test_absolute_paths_are_left_alone(tmp_path):
    database = "sqlite:///" + (tmp_path / "x.db").as_posix()

    loaded = Settings(_env_file=None, ENVIRONMENT="development", UPLOAD_TEMP_DIR=str(tmp_path), DATABASE_URL=database)

    assert loaded.UPLOAD_TEMP_DIR == str(tmp_path) and loaded.DATABASE_URL == database


def test_the_secret_refusal_tells_a_developer_what_to_do():
    with pytest.raises(ValueError, match=r"\.env\.example"):
        Settings(_env_file=None, ENVIRONMENT="production")


# --- a request body is refused while it arrives -------------------------------------------------

def test_a_body_larger_than_the_limit_is_refused_by_its_announced_length(monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 1024)

    response = client.post("/api/v1/sessions/any/submit", content=b"x" * 200_000, headers={"content-type": "multipart/form-data; boundary=x"})

    assert response.status_code == 413 and "limit" in response.json()["detail"]


def test_a_body_larger_than_the_limit_is_refused_even_without_a_content_length(monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 1024)
    start = b'--x\r\nContent-Disposition: form-data; name="media"; filename="a.webm"\r\nContent-Type: video/webm\r\n\r\n'
    chunks = (start if i == 0 else b"x" * 4096 for i in range(100))  # sent chunked: no Content-Length to check up front

    response = client.post("/api/v1/sessions/any/submit", content=chunks, headers={"content-type": "multipart/form-data; boundary=x"})

    assert response.status_code == 413


def test_a_body_within_the_limit_reaches_the_endpoint():
    response = client.post("/api/v1/sessions/unknown/submit", data={"token": "t"}, files={"media": ("a.webm", b"abc", "video/webm")})

    assert response.status_code == 404  # the endpoint answered: there is no such session


# --- readiness -----------------------------------------------------------------------------------

def test_ready_when_the_required_models_are_loaded():
    orchestrator.warm_up()

    response = client.get("/ready")

    assert response.status_code == 200 and response.json()["ready"] is True
    assert response.json()["models"]["speech_recognizer"] is None


def test_not_ready_when_a_required_model_is_missing_but_the_optional_one_may_be(monkeypatch):
    base = {"speech_detector": None, "speech_recognizer": None, "face_landmarker": None, "deepfake": None}

    monkeypatch.setattr(orchestrator, "model_status", lambda: {**base, "face_landmarker": "model file missing"})
    broken = client.get("/ready")
    monkeypatch.setattr(orchestrator, "model_status", lambda: {**base, "deepfake": "checkpoint missing"})
    optional_missing = client.get("/ready")

    assert broken.status_code == 503 and broken.json()["models"]["face_landmarker"] == "model file missing"
    assert optional_missing.status_code == 200 and optional_missing.json()["ready"] is True


def test_health_stays_a_plain_liveness_answer():
    assert client.get("/health").json()["status"] == "healthy"


# --- the demo endpoint has the same hard limits as a session ------------------------------------

def _verify(path):
    with open(path, "rb") as f:
        return client.post(
            "/api/v1/verify",
            data={"visual_challenge": "LOOK_UP", "verbal_challenge": "one two three four five"},
            files={"video": ("clip.webm", f, "video/webm")},
        )


@pytest.mark.parametrize("fixture", ["oversized_picture_webm", "long_recording_webm", "garbage_webm"])
def test_verify_refuses_what_a_session_would_refuse_and_keeps_nothing(fixture, request):
    response = _verify(request.getfixturevalue(fixture))

    assert response.status_code == 422
    assert list(Path(settings.UPLOAD_TEMP_DIR).glob("verify_*")) == []


# --- start-up sweep ------------------------------------------------------------------------------

def test_the_sweep_removes_leftover_media_and_nothing_else(tmp_path):
    tmp_path = tmp_path / "uploads"  # the test database lives next to tmp_path's other files
    tmp_path.mkdir()
    (tmp_path / "upload_1.webm").write_bytes(b"face")
    (tmp_path / "verify_2.mp4").write_bytes(b"face")
    (tmp_path / "old-session.webm").write_bytes(b"face")
    (tmp_path / "audio_xyz").mkdir()
    (tmp_path / "audio_xyz" / "speak.wav").write_bytes(b"voice")
    (tmp_path / "notes.txt").write_text("keep me")

    removed = housekeeping.sweep_leftover_media(tmp_path)

    assert removed == 4
    assert sorted(p.name for p in tmp_path.iterdir()) == ["notes.txt"]
    assert housekeeping.sweep_leftover_media(tmp_path / "missing") == 0
