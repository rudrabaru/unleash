"""Helpers for tests that run the orchestrator with mocked frame extraction and detectors."""
from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

import numpy as np

from app.media.frames import FrameBundle
from app.schemas.detector import DetectorResult

MOCK_PHRASE = "apple bridge cloud dark eagle"
FRAME = np.zeros((64, 64, 3), dtype=np.uint8)


def detector_result(score=0.90, passed=True, reason="ok", error=None, details=None):
    return DetectorResult(score=score, passed=passed, reason=reason, error=error, details=details or {})


def frame_bundle(count: int, error=None) -> FrameBundle:
    """A bundle of `count` identical blank frames; count 0 gives an error bundle with no frames."""
    if count == 0:
        return FrameBundle(error=error)
    times = [i / 30 for i in range(count)]
    return FrameBundle(
        dense=[FRAME] * count, dense_times=times, dense_indices=list(range(count)),
        sparse=[FRAME] * count, sparse_times=times, sparse_indices=list(range(count)),
        fps=30.0, error=error,
    )


@contextmanager
def mocked_detectors(*, audio, liveness, challenge, deepfake, replay, frames=5, frame_error=None):
    """Patch extraction and every detector.

    Each detector argument is a DetectorResult (returned when called), an Exception (raised
    when called) or a function (called instead).
    """
    with ExitStack() as stack:
        stack.enter_context(patch("app.orchestrator.load_frames", return_value=frame_bundle(frames, frame_error)))
        stack.enter_context(
            patch("app.orchestrator.extract_landmark_features", return_value={"frames": [], "error": None})
        )
        mocks = {}
        for name, target, value in (
            ("audio", "process_audio_pipeline", audio),
            ("liveness", "detect_visual_liveness", liveness),
            ("challenge", "verify_challenge_compliance", challenge),
            ("deepfake", "detect_deepfake", deepfake),
            ("replay", "detect_replay_attack", replay),
        ):
            mock = stack.enter_context(patch(f"app.orchestrator.{target}", new_callable=MagicMock))
            if isinstance(value, Exception) or callable(value):
                mock.side_effect = value
            else:
                mock.return_value = value
            mocks[name] = mock
        yield mocks
