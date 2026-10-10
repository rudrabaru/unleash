"""
Orchestrator tests with mocked detectors and a dummy media path.

They cover the data flow (extraction -> detectors -> fusion -> database), isolation of a
crashing detector, and a recording with no video. They do not claim a VERIFIED verdict on a
real recording; see test_analysis_integration.py for the real detectors.
"""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import db, orchestrator
from app.schemas.session import VerificationStatus
from _mocks import MOCK_PHRASE, detector_result as _detector_result, mocked_detectors as _mocked

PHRASE = MOCK_PHRASE


def _create_session(session_id: str, visual: str = "TURN_HEAD_LEFT") -> None:
    db.create_session(
        session_id=session_id,
        status="PENDING",
        visual_challenge=visual,
        verbal_challenge=PHRASE,
        created_at=datetime.now(timezone.utc),
    )


def _run_verification(session_id: str, visual: str = "TURN_HEAD_LEFT") -> None:
    orchestrator.run_verification(
        session_id=session_id,
        media_path=Path("dummy_video.webm"),
        visual_challenge=visual,
        verbal_challenge=PHRASE,
    )


def test_all_signals_flow_through_fusion_into_the_database():
    _create_session("all-pass")
    with _mocked(
        audio=_detector_result(
            0.92, True, "Audio speech matched", details={"voice_authenticity_score": 0.88, "av_alignment_score": 0.85}
        ),
        liveness=_detector_result(0.95, True, "Natural blink detected"),
        challenge=_detector_result(1.00, True, "Head turn left complied"),
        deepfake=_detector_result(0.90, True, "Real video classified"),
        replay=_detector_result(0.85, True, "Genuine display"),
    ):
        _run_verification("all-pass")

    saved = db.get_session("all-pass")
    assert saved["status"] == VerificationStatus.VERIFIED.value
    assert saved["confidence"] >= 0.80
    assert set(saved["signals"]) == {"audio_pipeline", "visual_liveness", "visual_challenge", "deepfake", "replay"}
    assert saved["signals"]["visual_challenge"].passed is True
    assert saved["signals"]["audio_pipeline"].passed is True


def test_null_scores_are_stored_as_null_and_excluded_from_the_weighted_score():
    _create_session("null-scores", "TURN_HEAD_RIGHT")
    with _mocked(
        audio=_detector_result(1.0, True, "Speech passed", details={"voice_authenticity_score": None}),
        liveness=_detector_result(0.90, True, "Liveness ok"),
        challenge=_detector_result(1.00, True, "Turn right ok"),
        deepfake=_detector_result(score=None, passed=False, reason="Checkpoint missing", error="missing"),
        replay=_detector_result(score=None, passed=False, reason="Uncalibrated"),
    ):
        _run_verification("null-scores", "TURN_HEAD_RIGHT")

    saved = db.get_session("null-scores")
    assert saved["signals"]["deepfake"].score is None
    assert saved["signals"]["replay"].score is None
    # Only liveness (weight 0.20) and challenge (weight 0.25) are measured, so their weights
    # are redistributed over those two: (0.20*0.90 + 0.25*1.00) / 0.45
    assert saved["confidence"] == pytest.approx((0.20 * 0.90 + 0.25 * 1.00) / 0.45, abs=1e-3)


def test_crashing_detector_is_isolated_and_fails_closed():
    _create_session("crash")
    with _mocked(
        audio=_detector_result(1.0, True, "Audio passed"),
        liveness=_detector_result(0.90, True, "Liveness ok"),
        challenge=_detector_result(1.00, True, "Challenge ok"),
        deepfake=RuntimeError("Out of memory in inference"),
        replay=_detector_result(0.80, True, "Replay ok"),
    ):
        _run_verification("crash")

    saved = db.get_session("crash")
    deepfake = saved["signals"]["deepfake"]
    assert deepfake.score is None
    assert deepfake.passed is False
    assert "Out of memory" in deepfake.error
    # the other detectors still ran and were stored
    assert saved["signals"]["replay"].score == 0.80


def test_recording_without_video_fails_the_video_signals_with_the_extraction_error():
    _create_session("no-video")
    with _mocked(
        audio=_detector_result(1.0, True, "Audio passed"),
        liveness=_detector_result(0.90, True, "not reached"),
        challenge=_detector_result(1.00, True, "not reached"),
        deepfake=_detector_result(0.90, True, "not reached"),
        replay=_detector_result(0.80, True, "not reached"),
        frames=0,
        frame_error="No video stream in media file.",
    ) as mocks:
        _run_verification("no-video")

    for name in ("liveness", "challenge", "deepfake", "replay"):
        mocks[name].assert_not_called()
    saved = db.get_session("no-video")
    assert saved["status"] == VerificationStatus.FAILED.value
    for name in orchestrator.VIDEO_SIGNALS:
        signal = saved["signals"][name]
        assert signal.score is None and signal.passed is False
        assert signal.error == "No video stream in media file."
    assert saved["signals"]["audio_pipeline"].passed is True


def test_analyze_media_reports_timings_for_every_step():
    with _mocked(
        audio=_detector_result(1.0, True, "Audio passed"),
        liveness=_detector_result(0.90, True, "Liveness ok"),
        challenge=_detector_result(1.00, True, "Challenge ok"),
        deepfake=_detector_result(0.90, True, "Deepfake ok"),
        replay=_detector_result(0.80, True, "Replay ok"),
    ):
        analysis = orchestrator.analyze_media(Path("dummy_video.webm"), "TURN_HEAD_LEFT", PHRASE)

    assert set(analysis.timings) == {
        "frames", "landmarks", "probe", "audio", "visual_liveness", "visual_challenge", "deepfake", "replay", "fusion", "total",
    }


def test_warm_up_reports_a_model_that_cannot_load_and_does_not_raise():
    from unittest.mock import patch

    from app import orchestrator

    with patch("app.modules.antispoof._deepfake.classifier._load_model", side_effect=RuntimeError("no checkpoint")):
        failures = orchestrator.warm_up()
    assert failures == {"deepfake": "no checkpoint"}
