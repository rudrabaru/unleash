import cv2
import math
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from config import MODEL_PATH

# MEDIAPIPE
options = vision.FaceLandmarkerOptions(
    base_options=python.BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=vision.RunningMode.VIDEO,
    num_faces=1,
    output_face_blendshapes=True,
    output_facial_transformation_matrixes=True,
    min_face_detection_confidence=0.5,
    min_face_presence_confidence=0.5,
    min_tracking_confidence=0.5,
)

def get_blendshape_scores(result):
    if not result.face_blendshapes:
        return {}
    return {
        item.category_name: float(item.score)
        for item in result.face_blendshapes[0]
    }

def rotation_matrix_to_euler(matrix):
    # Validated convention:
    # physical LEFT -> positive yaw
    # physical RIGHT -> negative yaw

    r00 = matrix[0][0]
    r02 = matrix[0][2]
    r10 = matrix[1][0]
    r11 = matrix[1][1]
    r12 = matrix[1][2]

    yaw = math.atan2(r02, r00)
    pitch = math.atan2(-r12, r11)
    roll = math.atan2(
        r10,
        math.sqrt(r00 * r00 + r02 * r02)
    )

    return (
        math.degrees(yaw),
        math.degrees(pitch),
        math.degrees(roll),
    )

def process_video(video_path):
    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if fps <= 0:
        fps = 30.0

    frames = []
    frame_index = 0
    last_timestamp_ms = -1

    try:
        with vision.FaceLandmarker.create_from_options(options) as landmarker:
            while True:
                success, frame = cap.read()
                if not success:
                    break

                timestamp = frame_index / fps
                timestamp_ms = int(timestamp * 1000)
                if timestamp_ms <= last_timestamp_ms:
                    timestamp_ms = last_timestamp_ms + 1
                last_timestamp_ms = timestamp_ms

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                mp_image = mp.Image(
                    image_format=mp.ImageFormat.SRGB,
                    data=rgb
                )

                result = landmarker.detect_for_video(
                    mp_image,
                    timestamp_ms
                )

                landmarks = (
                    np.array([[lm.x, lm.y] for lm in result.face_landmarks[0]], dtype=np.float32)
                    if result.face_landmarks else None
                )

                frame_data = {
                    "timestamp": timestamp,
                    "landmarks": landmarks,
                    "face_present": bool(result.face_landmarks),
                    "yaw": None,
                    "pitch": None,
                    "roll": None,
                    "blink_left": None,
                    "blink_right": None,
                    "mouth_open": None,
                    "mouth_open_raw": None,
                }

                if result.face_landmarks:
                    blendshapes = get_blendshape_scores(result)

                    frame_data["blink_left"] = blendshapes.get("eyeBlinkLeft")
                    frame_data["blink_right"] = blendshapes.get("eyeBlinkRight")

                    mouth_open = calculate_mouth_openness(landmarks)
                    frame_data["mouth_open"] = mouth_open
                    frame_data["mouth_open_raw"] = mouth_open

                if result.facial_transformation_matrixes:
                    matrix = result.facial_transformation_matrixes[0]
                    yaw, pitch, roll = rotation_matrix_to_euler(matrix)

                    frame_data["yaw"] = yaw
                    frame_data["pitch"] = pitch
                    frame_data["roll"] = roll

                frames.append(frame_data)
                frame_index += 1
    finally:
        cap.release()

    smooth_mouth_signal(frames)
    return {
        "fps": fps,
        "frame_count": frame_index,
        "duration": frame_index / fps if fps > 0 else 0.0,
        "frames": frames,
    }

def calculate_mouth_openness(landmarks):
    if landmarks is None:
        return None

    # Vertical mouth distances
    d1 = np.linalg.norm(landmarks[13] - landmarks[14])
    d2 = np.linalg.norm(landmarks[82] - landmarks[87])
    d3 = np.linalg.norm(landmarks[312] - landmarks[317])

    # Horizontal mouth width
    width = np.linalg.norm(
        landmarks[61] - landmarks[291]
    )

    if width < 1e-6:
        return None

    # Mouth Aspect Ratio (MAR)
    mar = (d1 + d2 + d3) / (3.0 * width)
    return float(mar)

def smooth_mouth_signal(frames, window=5):
    valid_indices = [
        i
        for i, frame in enumerate(frames)
        if frame["mouth_open"] is not None
    ]

    values = [
        frames[i]["mouth_open"]
        for i in valid_indices
    ]

    if not values:
        return

    smoothed = []

    for i in range(len(values)):
        start = max(0, i - window // 2)
        end = min(
            len(values),
            i + window // 2 + 1
        )

        smoothed.append(
            float(np.median(values[start:end]))
        )

    for index, value in zip(valid_indices, smoothed):
        frames[index]["mouth_open"] = value