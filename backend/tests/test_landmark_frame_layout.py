"""
Regression: frames whose width is not a multiple of 16 come out of the decoder with padded rows
(non-contiguous numpy arrays). MediaPipe read them as scrambled images and silently found no face,
so every such recording ended in RETRY. Found while evaluating on GRID video (360 px wide).
"""
import shutil
import subprocess

import numpy as np
import pytest

from app.media.frames import DENSE_MAX_EDGE, load_frames
from app.modules.visual import extract_landmark_features

from _paths import VIDEO_FIXTURES_DIR, require


def _face_frame():
    bundle = load_frames(require(VIDEO_FIXTURES_DIR / "TURN_LEFT.webm"))
    return bundle.dense[0]


def test_a_non_contiguous_frame_still_shows_its_face():
    frame = _face_frame()
    h, w, _ = frame.shape
    padded = np.zeros((h, w + 8, 3), dtype=frame.dtype)
    padded[:, :w] = frame
    view = padded[:, :w]  # same pixels, padded rows: what the decoder returns at such widths
    assert not view.flags["C_CONTIGUOUS"]

    assert extract_landmark_features([view])["frames"][0]["face_present"] is True


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_a_360_pixel_wide_recording_is_judged(tmp_path):
    source = require(VIDEO_FIXTURES_DIR / "TURN_LEFT.webm")
    narrow = tmp_path / "narrow.webm"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-t", "1",
         "-vf", "scale=360:-2", "-c:v", "libvpx", "-b:v", "1M", "-an", str(narrow)],
        check=True,
    )
    bundle = load_frames(narrow, dense_max_edge=DENSE_MAX_EDGE)
    assert bundle.dense and bundle.dense[0].shape[1] == 360

    frames = extract_landmark_features(bundle.dense[:5])["frames"]

    assert sum(f["face_present"] for f in frames) >= 4
