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
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = []
    frame_index = 0

    with vision.FaceLandmarker.create_from_options(options) as landmarker:
        while True:
            success, frame = cap.read()
            if not success:
                break

            timestamp = frame_index / fps
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=rgb
            )

            result = landmarker.detect_for_video(
                mp_image,
                int(timestamp * 1000)
            )
            landmarks = (np.array([[lm.x, lm.y] for lm in result.face_landmarks[0]],dtype=np.float32) if result.face_landmarks else None),

            frame_data = {
                "timestamp": timestamp,
                "landmarks" : landmarks,
                "face_present": bool(result.face_landmarks),
                "yaw": None,
                "pitch": None,
                "roll": None,
                "blink_left": None,
                "blink_right": None,
            }

            if result.face_landmarks:
                blendshapes = get_blendshape_scores(result)

                frame_data["blink_left"] = blendshapes.get(
                    "eyeBlinkLeft"
                )
                frame_data["blink_right"] = blendshapes.get(
                    "eyeBlinkRight"
                )

            if result.facial_transformation_matrixes:
                matrix = result.facial_transformation_matrixes[0]

                yaw, pitch, roll = rotation_matrix_to_euler(matrix)

                frame_data["yaw"] = yaw
                frame_data["pitch"] = pitch
                frame_data["roll"] = roll

            frames.append(frame_data)
            frame_index += 1

    cap.release()

    return {
        "fps": fps,
        "frame_count": frame_index,
        "duration": frame_index / fps,
        "frames": frames,
    }