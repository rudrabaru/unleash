"""Haar-cascade primary face crop, ported from deepfake_detection/app/video.py."""
import numpy as np

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:  # pragma: no cover
    CV2_AVAILABLE = False


def crop_primary_face(frame: np.ndarray) -> np.ndarray:
    if not CV2_AVAILABLE or not hasattr(cv2, "CascadeClassifier") or not hasattr(cv2, "data"):
        return frame

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_detector = cv2.CascadeClassifier(cascade_path)
    if face_detector.empty():
        return frame

    gray_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
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
