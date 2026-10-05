"""
The analysis must not block the server's event loop, must never run two analyses at once
(the speech detector and the MediaPipe landmarker are shared), and a session can be claimed
for processing by only one request.
"""
import inspect
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from app import db, orchestrator
from app.api.v1.endpoints import sessions, verify
from app.modules.antispoof import detect_deepfake, detect_replay_attack
from app.modules.audio import process_audio_pipeline
from app.modules.visual import detect_visual_liveness, verify_challenge_compliance
from _mocks import MOCK_PHRASE, detector_result, mocked_detectors


def test_blocking_work_is_not_declared_async():
    """Plain functions run in the server's thread pool; `async def` would run them on the event loop."""
    blocking = [
        detect_visual_liveness, verify_challenge_compliance, detect_deepfake, detect_replay_attack,
        process_audio_pipeline, orchestrator.analyze_media, orchestrator.run_verification,
        sessions.create_session, sessions.submit_session, sessions.get_session_result,
        sessions._run_and_cleanup, verify.verify_clip,
    ]
    assert [f.__name__ for f in blocking if inspect.iscoroutinefunction(f)] == []


def test_two_analyses_never_run_at_the_same_time():
    running = 0
    peak = 0
    guard = threading.Lock()

    def slow_audio(*args, **kwargs):
        nonlocal running, peak
        with guard:
            running += 1
            peak = max(peak, running)
        time.sleep(0.15)
        with guard:
            running -= 1
        return detector_result(1.0, True, "Audio passed")

    with mocked_detectors(
        audio=slow_audio,
        liveness=detector_result(0.9),
        challenge=detector_result(1.0),
        deepfake=detector_result(0.9),
        replay=detector_result(0.8),
    ):
        threads = [
            threading.Thread(target=orchestrator.analyze_media, args=(Path("a.webm"), "TURN_HEAD_LEFT", MOCK_PHRASE))
            for _ in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert peak == 1


def test_a_session_can_be_claimed_for_processing_only_once():
    db.create_session("claim-me", "CREATED", "TURN_HEAD_LEFT", MOCK_PHRASE, datetime.now(timezone.utc))

    assert db.claim_for_processing("claim-me", datetime.now(timezone.utc)) is True
    assert db.claim_for_processing("claim-me", datetime.now(timezone.utc)) is False
    assert db.get_session("claim-me")["status"] == "PROCESSING"
