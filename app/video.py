from pathlib import Path

import cv2
import numpy as np


SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


class VideoProcessingError(Exception):
    """Raised when uploaded video frames cannot be sampled."""


def is_supported_video(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS


def sample_video_frames(video_path: str, max_frames: int) -> list[np.ndarray]:
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise VideoProcessingError("Could not open uploaded video.")

    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_indexes = _sample_indexes(frame_count, max_frames)
    frames: list[np.ndarray] = []

    if frame_indexes:
        for frame_index in frame_indexes:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            success, frame = capture.read()
            if success and frame is not None:
                frames.append(frame)
    else:
        while len(frames) < max_frames:
            success, frame = capture.read()
            if not success or frame is None:
                break
            frames.append(frame)

    capture.release()

    if not frames:
        raise VideoProcessingError("No readable frames were found in the video.")
    return frames


def crop_primary_face(frame: np.ndarray) -> np.ndarray:
    if not hasattr(cv2, "CascadeClassifier") or not hasattr(cv2, "data"):
        return frame

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_detector = cv2.CascadeClassifier(cascade_path)
    if face_detector.empty():
        return frame

    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_detector.detectMultiScale(gray_frame, scaleFactor=1.1, minNeighbors=5)
    if len(faces) == 0:
        return frame

    x, y, width, height = max(faces, key=lambda face: face[2] * face[3])
    padding = int(0.15 * max(width, height))
    top = max(y - padding, 0)
    left = max(x - padding, 0)
    bottom = min(y + height + padding, frame.shape[0])
    right = min(x + width + padding, frame.shape[1])
    return frame[top:bottom, left:right]


def _sample_indexes(frame_count: int, max_frames: int) -> list[int]:
    if frame_count <= 0:
        return []

    total = min(frame_count, max_frames)
    if total <= 1:
        return [0]

    indexes = np.linspace(0, frame_count - 1, total, dtype=int)
    return sorted(set(indexes.tolist()))
