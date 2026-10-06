"""Face crops for the deepfake step: box geometry and frame/landmark matching."""
import numpy as np

from app.media.face_crop import MIN_CROP_PIXELS, crop_faces, face_box


def _landmarks(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y1], [(x0 + x1) / 2, (y0 + y1) / 2]], dtype=np.float32)


def test_box_is_square_scaled_and_centred():
    x0, y0, x1, y1 = face_box(_landmarks(0.4, 0.3, 0.6, 0.7), width=1000, height=1000, scale=1.0)
    assert (x1 - x0) == (y1 - y0) == 400  # larger side (0.4 * 1000), unscaled
    assert (x0 + x1) / 2 == 500 and (y0 + y1) / 2 == 500


def test_box_is_clamped_to_the_frame():
    x0, y0, x1, y1 = face_box(_landmarks(0.0, 0.0, 0.5, 0.5), width=800, height=600)
    assert x0 == 0 and y0 == 0 and x1 <= 800 and y1 <= 600


def test_tiny_or_missing_face_gives_no_box():
    assert face_box(_landmarks(0.5, 0.5, 0.5 + 10 / 1000, 0.5 + 10 / 1000), 1000, 1000, scale=1.0) is None
    assert face_box(None, 100, 100) is None
    assert MIN_CROP_PIXELS > 0


def test_crop_faces_matches_by_stream_index_and_skips_frames_without_a_face():
    frames = [np.zeros((480, 640, 3), np.uint8) for _ in range(3)]
    features = {
        "error": None,
        "frames": [
            {"original_index": 10, "face_present": True, "landmarks": _landmarks(0.3, 0.3, 0.7, 0.8)},
            {"original_index": 20, "face_present": False, "landmarks": None},
            {"original_index": 30, "face_present": True, "landmarks": _landmarks(0.3, 0.3, 0.7, 0.8)},
        ],
    }
    crops = crop_faces(frames, [10, 20, 30], features)
    assert len(crops) == 2
    assert all(c.shape[0] > 0 and c.shape[1] > 0 for c in crops)


def test_crop_faces_without_landmarks_returns_nothing():
    frames = [np.zeros((480, 640, 3), np.uint8)]
    assert crop_faces(frames, [0], None) == []
    assert crop_faces(frames, [0], {"error": "x", "frames": []}) == []
