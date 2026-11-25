"""
Tests for the small pieces between the media file and the detectors: the ffmpeg/ffprobe lookup,
the speech-check hand-off, and the shared MediaPipe landmarker.
"""
from __future__ import annotations

import math
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import soundfile as sf

from app.modules.audio import _Prepared, _run_checks
from app.modules.audio import _extraction as extraction
from app.modules.visual import _landmarks as landmarks
from app.schemas.detector import DetectorResult
from _paths import GENUINE_5WORD_PHRASE, GENUINE_5WORD_WEBM, require


# --- ffmpeg / ffprobe are looked up when they are used -------------------------------------------

def test_missing_ffprobe_is_a_reported_failure_not_a_crash(monkeypatch):
    clip = require(GENUINE_5WORD_WEBM)
    monkeypatch.setattr(extraction.shutil, "which", lambda name: None)
    info = extraction.probe_media(clip)
    assert info["ok"] is False
    assert "ffprobe executable not found" in info["error"]


def test_missing_ffmpeg_is_a_reported_failure_not_a_crash(monkeypatch, tmp_path):
    clip = require(GENUINE_5WORD_WEBM)
    monkeypatch.setattr(extraction.shutil, "which", lambda name: None)
    ok, error, seconds = extraction.extract_wav(clip, tmp_path / "out.wav")
    assert ok is False
    assert "ffmpeg executable not found" in error
    assert seconds == 0.0


def test_tools_are_found_again_once_they_are_on_the_path(monkeypatch):
    """The lookup happens per call, so a tool installed after import is picked up (no stale None)."""
    clip = require(GENUINE_5WORD_WEBM)
    with monkeypatch.context() as hidden:
        hidden.setattr(extraction.shutil, "which", lambda name: None)
        assert extraction.probe_media(clip)["ok"] is False
    assert extraction.probe_media(clip)["ok"] is True


# --- a failed speech check ends the pipeline and is returned as it is ----------------------------

def test_failed_speech_check_is_returned_unchanged(monkeypatch, tmp_path):
    noise = tmp_path / "noise.wav"
    sf.write(str(noise), np.random.default_rng(0).normal(0, 0.05, 16000).astype(np.float32), 16000)
    failed = DetectorResult(
        score=None, passed=False, reason="No speech detected in audio submission.", error=None,
        details={"speech_detected": False, "speech_duration_seconds": 0.0, "segments": []},
    )
    monkeypatch.setattr("app.modules.audio.run_speech_gate", lambda wav_path: failed)
    monkeypatch.setattr(
        "app.modules.audio.run_phrase_compliance",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("the phrase check must not run")),
    )
    result = _run_checks(_Prepared(wav_path=noise), GENUINE_5WORD_PHRASE, None)
    assert result is failed


# --- landmarks -----------------------------------------------------------------------------------

def _fake_landmarker(face_landmarks, matrix):
    class Fake:
        def detect(self, _image):
            return SimpleNamespace(face_landmarks=face_landmarks, facial_transformation_matrixes=[matrix])

    return Fake()


def _matrix_with_yaw(degrees: float) -> np.ndarray:
    radians = math.radians(degrees)
    matrix = np.eye(4)
    matrix[0][0], matrix[0][2] = math.cos(radians), math.sin(radians)
    return matrix


def test_pose_is_not_reported_for_a_frame_without_a_face(monkeypatch):
    """MediaPipe can return a transformation matrix without landmarks; that must not become a yaw."""
    monkeypatch.setattr(landmarks, "_get_landmarker", lambda: _fake_landmarker([], _matrix_with_yaw(20)))
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    entry = landmarks.extract_landmark_features([frame])["frames"][0]
    assert entry["face_present"] is False
    assert entry["yaw"] is None and entry["pitch"] is None


def test_pose_is_reported_when_a_face_is_present(monkeypatch):
    rng = np.random.default_rng(0)
    points = [SimpleNamespace(x=float(x), y=float(y)) for x, y in rng.uniform(0.3, 0.7, size=(478, 2))]
    monkeypatch.setattr(landmarks, "_get_landmarker", lambda: _fake_landmarker([points], _matrix_with_yaw(20)))
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    entry = landmarks.extract_landmark_features([frame])["frames"][0]
    assert entry["face_present"] is True
    assert math.isclose(entry["yaw"], 20.0, abs_tol=1e-6)
    assert math.isclose(entry["pitch"], 0.0, abs_tol=1e-6)


def test_shared_landmarker_is_created_once_under_concurrent_first_use(monkeypatch):
    created = []
    gate = threading.Barrier(8)

    def slow_create(_options):
        created.append(1)
        threading.Event().wait(0.05)  # widen the window in which a second thread could also create one
        return object()

    monkeypatch.setattr(landmarks, "_landmarker_singleton", None)
    monkeypatch.setattr(landmarks.mp_vision.FaceLandmarker, "create_from_options", staticmethod(slow_create))

    def first_use(_):
        gate.wait()
        return landmarks._get_landmarker()

    with ThreadPoolExecutor(max_workers=8) as pool:
        instances = list(pool.map(first_use, range(8)))

    assert len(created) == 1
    assert all(instance is instances[0] for instance in instances)
