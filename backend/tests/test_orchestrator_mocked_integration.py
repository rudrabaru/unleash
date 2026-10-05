"""
Orchestrator Mocked Integration Test (Task D).
Explicitly note: This test uses MOCKED detector outputs and dummy media path.
It tests the orchestration, exception isolation, fusion invocation, and DB persistence.
It does NOT claim to prove end-to-end VERIFIED on real user media recordings
(which remains BLOCKED awaiting genuine multi-modal fixtures from Dev 1 & Dev 2).
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from app import db, orchestrator
from app.modules.frame_extraction import FrameExtractionResult
from app.schemas.detector import DetectorResult
from app.schemas.session import VerificationStatus


def _dummy_detector_result(score=0.90, passed=True, reason="ok", error=None, details=None):
    return DetectorResult(
        score=score,
        passed=passed,
        reason=reason,
        error=error,
        details=details or {},
    )


def test_orchestrator_mocked_integration_flow_all_pass():
    """
    Simulate full orchestrator execution when all five modules succeed.
    Verifies data flow: extraction -> mock detectors -> fusion -> db persistence.
    """
    session_id = "mocked-session-all-pass"
    now = datetime.now(timezone.utc)
    db.create_session(
        session_id=session_id,
        status="PENDING",
        visual_challenge="TURN_HEAD_LEFT",
        verbal_challenge="apple bridge cloud dark eagle",
        created_at=now,
    )

    dummy_frame = np.zeros((64, 64, 3), dtype=np.uint8)
    mock_frame_res = FrameExtractionResult(
        frames=[dummy_frame] * 5,
        fps=30.0,
        timestamps=[0.0, 0.033, 0.067, 0.1, 0.133],
        error=None,
    )

    with patch("app.orchestrator.extract_frames", return_value=mock_frame_res), \
         patch("app.orchestrator.extract_landmark_features", return_value={"landmarks": []}), \
         patch("app.orchestrator.build_lip_series", return_value={"fps": 30.0, "series": []}), \
         patch("app.orchestrator.process_audio_pipeline", new_callable=AsyncMock) as mock_audio, \
         patch("app.orchestrator.detect_visual_liveness", new_callable=AsyncMock) as mock_live, \
         patch("app.orchestrator.verify_challenge_compliance", new_callable=AsyncMock) as mock_chal, \
         patch("app.orchestrator.detect_deepfake", new_callable=AsyncMock) as mock_df, \
         patch("app.orchestrator.detect_replay_attack", new_callable=AsyncMock) as mock_rep:

        mock_audio.return_value = _dummy_detector_result(
            0.92, True, "Audio speech matched", details={"voice_authenticity_score": 0.88, "av_alignment_score": 0.85}
        )
        mock_live.return_value = _dummy_detector_result(0.95, True, "Natural blink detected")
        mock_chal.return_value = _dummy_detector_result(1.00, True, "Head turn left complied")
        mock_df.return_value = _dummy_detector_result(0.90, True, "Real video classified")
        mock_rep.return_value = _dummy_detector_result(0.85, True, "Genuine display")

        asyncio.run(
            orchestrator.run_verification(
                session_id=session_id,
                media_path=Path("dummy_video.webm"),
                visual_challenge="TURN_HEAD_LEFT",
                verbal_challenge="apple bridge cloud dark eagle",
            )
        )

    saved = db.get_session(session_id)
    assert saved is not None
    assert saved["status"] == VerificationStatus.VERIFIED.value
    assert saved["confidence"] is not None
    assert saved["confidence"] >= 0.80
    assert "signals" in saved
    assert saved["signals"]["visual_challenge"].passed is True
    assert saved["signals"]["audio_pipeline"].passed is True


def test_orchestrator_mocked_integration_flow_with_null_scores():
    """
    Simulate orchestrator flow when uncalibrated/optional modules return score=None.
    Verifies that fusion redistributes weight and DB correctly preserves nulls.
    """
    session_id = "mocked-session-null-scores"
    now = datetime.now(timezone.utc)
    db.create_session(
        session_id=session_id,
        status="PENDING",
        visual_challenge="TURN_HEAD_RIGHT",
        verbal_challenge="apple bridge cloud dark eagle",
        created_at=now,
    )

    # The orchestrator fails every video detector when no frames exist at all, so this test
    # supplies frames: it is about null detector scores, not about missing video.
    dummy_frame = np.zeros((64, 64, 3), dtype=np.uint8)
    mock_frame_res = FrameExtractionResult(frames=[dummy_frame] * 5, fps=30.0, timestamps=[0.0, 0.033, 0.067, 0.1, 0.133], error=None)

    with patch("app.orchestrator.extract_frames", return_value=mock_frame_res), \
         patch("app.orchestrator.process_audio_pipeline", new_callable=AsyncMock) as mock_audio, \
         patch("app.orchestrator.detect_visual_liveness", new_callable=AsyncMock) as mock_live, \
         patch("app.orchestrator.verify_challenge_compliance", new_callable=AsyncMock) as mock_chal, \
         patch("app.orchestrator.detect_deepfake", new_callable=AsyncMock) as mock_df, \
         patch("app.orchestrator.detect_replay_attack", new_callable=AsyncMock) as mock_rep:

        mock_audio.return_value = _dummy_detector_result(1.0, True, "Speech passed", details={"voice_authenticity_score": None})
        mock_live.return_value = _dummy_detector_result(0.90, True, "Liveness ok")
        mock_chal.return_value = _dummy_detector_result(1.00, True, "Turn right ok")
        mock_df.return_value = _dummy_detector_result(score=None, passed=False, reason="Checkpoint missing", error="missing")
        mock_rep.return_value = _dummy_detector_result(score=None, passed=False, reason="Uncalibrated", error=None)

        asyncio.run(
            orchestrator.run_verification(
                session_id=session_id,
                media_path=Path("dummy_video.webm"),
                visual_challenge="TURN_HEAD_RIGHT",
                verbal_challenge="apple bridge cloud dark eagle",
            )
        )

    saved = db.get_session(session_id)
    assert saved is not None
    assert saved["status"] == VerificationStatus.VERIFIED.value
    assert saved["confidence"] is not None
    # Replay and deepfake scores were None and excluded from weighted denominator
    assert saved["signals"]["deepfake"].score is None
    assert saved["signals"]["replay"].score is None


def test_orchestrator_isolates_crashing_detector():
    """
    Verify that if an individual detector raises an uncaught exception,
    _safe_call isolates it and does not crash the orchestrator or session processing.
    """
    session_id = "mocked-session-crashing-module"
    now = datetime.now(timezone.utc)
    db.create_session(
        session_id=session_id,
        status="PENDING",
        visual_challenge="TURN_HEAD_LEFT",
        verbal_challenge="apple bridge cloud dark eagle",
        created_at=now,
    )

    mock_frame_res = FrameExtractionResult(frames=[], fps=0.0, timestamps=[], error=None)

    with patch("app.orchestrator.extract_frames", return_value=mock_frame_res), \
         patch("app.orchestrator.process_audio_pipeline", new_callable=AsyncMock) as mock_audio, \
         patch("app.orchestrator.detect_visual_liveness", new_callable=AsyncMock) as mock_live, \
         patch("app.orchestrator.verify_challenge_compliance", new_callable=AsyncMock) as mock_chal, \
         patch("app.orchestrator.detect_deepfake", new_callable=AsyncMock) as mock_df, \
         patch("app.orchestrator.detect_replay_attack", new_callable=AsyncMock) as mock_rep:

        mock_audio.return_value = _dummy_detector_result(1.0, True, "Audio passed")
        mock_live.return_value = _dummy_detector_result(0.90, True, "Liveness ok")
        mock_chal.return_value = _dummy_detector_result(1.00, True, "Challenge ok")
        # Deepfake crashes unexpectedly
        mock_df.side_effect = RuntimeError("Out of memory in inference")
        mock_rep.return_value = _dummy_detector_result(0.80, True, "Replay ok")

        asyncio.run(
            orchestrator.run_verification(
                session_id=session_id,
                media_path=Path("dummy_video.webm"),
                visual_challenge="TURN_HEAD_LEFT",
                verbal_challenge="apple bridge cloud dark eagle",
            )
        )

    saved = db.get_session(session_id)
    assert saved is not None
    # Orchestrator caught the exception and marked deepfake failed closed
    df_signal = saved["signals"]["deepfake"]
    assert df_signal.score is None
    assert df_signal.passed is False
    assert "Out of memory" in df_signal.error
