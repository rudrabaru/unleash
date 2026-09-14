import numpy as np
import statistics

def calculate_micro_movement(features):
    frames = features["frames"]
    movements = []

    previous = None

    for frame in frames:
        current = frame["landmarks"]

        if current is None:
            previous = None
            continue

        current = np.asarray(
            current,
            dtype=np.float32
        ).squeeze()

        # We need exactly:
        # (number_of_landmarks, 2)
        if current.ndim != 2 or current.shape[1] != 2:
            previous = None
            continue

        if previous is None:
            previous = current
            continue

        if previous.shape != current.shape:
            previous = current
            continue

        displacement = np.linalg.norm(
            current - previous,
            axis=1
        )

        movements.append(
            float(np.mean(displacement))
        )

        previous = current

    if not movements:
        return {
            "mean_movement": 0.0,
            "median_movement": 0.0,
            "std_movement": 0.0,
            "max_movement": 0.0,
            "movement_samples": 0,
        }

    values = np.asarray(
        movements,
        dtype=np.float32
    )

    return {
        "mean_movement": float(np.mean(values)),
        "median_movement": float(np.median(values)),
        "std_movement": float(np.std(values)),
        "max_movement": float(np.max(values)),
        "movement_samples": len(values),
    }

def calculate_face_consistency(features):
    """
    Measure how consistently a usable face/landmark set is
    available throughout the video.

    Returns tracking statistics only.
    """
    frames = features["frames"]
    total_frames = len(frames)

    if total_frames == 0:
        return {
            "face_coverage": 0.0,
            "landmark_coverage": 0.0,
            "longest_missing_run": 0,
            "consistency_score": 0.0,
        }

    face_valid = [
        frame["face_present"]
        for frame in frames
    ]

    landmark_valid = [
        frame["landmarks"] is not None
        for frame in frames
    ]

    face_coverage = (
        sum(face_valid) / total_frames
    )

    landmark_coverage = (
        sum(landmark_valid) / total_frames
    )

    # Find the longest continuous period where
    # a usable face/landmark set is unavailable.
    longest_missing_run = 0
    current_missing_run = 0

    for valid in landmark_valid:
        if not valid:
            current_missing_run += 1
            longest_missing_run = max(
                longest_missing_run,
                current_missing_run
            )
        else:
            current_missing_run = 0

    consistency_score = (
        face_coverage +
        landmark_coverage
    ) / 2.0

    return {
        "face_coverage": face_coverage,
        "landmark_coverage": landmark_coverage,
        "longest_missing_run": longest_missing_run,
        "consistency_score": consistency_score,
    }

def calculate_baseline_angle(frames, key="yaw", baseline_seconds=0.5, fallback_frames=10):
    """
    Calculate baseline angle (yaw or pitch) from initial frames.
    Falls back to the first available valid frames if no face was
    detected in the first baseline_seconds.
    """
    values = [
        frame[key]
        for frame in frames
        if (
            frame.get(key) is not None
            and frame.get("timestamp", 0) <= baseline_seconds
        )
    ]

    # Fallback to the first available valid frames if initial window was empty
    if not values:
        values = [
            frame[key]
            for frame in frames
            if frame.get(key) is not None
        ][:fallback_frames]

    return statistics.median(values) if values else None

def calculate_baseline_yaw(frames, baseline_seconds=0.5):
    return calculate_baseline_angle(frames, key="yaw", baseline_seconds=baseline_seconds)

def calculate_baseline_pitch(frames, baseline_seconds=0.5):
    return calculate_baseline_angle(frames, key="pitch", baseline_seconds=baseline_seconds)
