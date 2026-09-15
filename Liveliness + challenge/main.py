import matplotlib.pyplot as plt
import numpy as np

from config import (
    BASELINE_SECONDS,
    HEAD_TURN_THRESHOLD,
    HEAD_HOLD_FRAMES,
    BLINK_THRESHOLD,
    BLINK_HOLD_FRAMES,
    MOUTH_THRESHOLD,
    MOUTH_HOLD_FRAMES,
)

from calculation import (
    calculate_face_consistency,
    calculate_micro_movement,
)
from scoring import (
    score_blink,
    score_micro_movement,
    calculate_visual_liveness,
)
from challenge_detector import (
    analyze_blink,
    analyze_head_turn,
    analyze_vertical_turn,
    analyze_mouth_open,
)
from video_process import (
    process_video,
)

SHOW_LIVENESS = True
SHOW_DIAGNOSTICS = False
SHOW_MOUTH = True

def normalize_challenge(challenge):
    name = challenge.strip().upper().replace(" ", "_")
    mapping = {
        "LOOK_UP": "TURN_UP",
        "UP": "TURN_UP",
        "LOOK_DOWN": "TURN_DOWN",
        "DOWN": "TURN_DOWN",
        "LEFT": "TURN_LEFT",
        "RIGHT": "TURN_RIGHT",
        "MOUTH": "OPEN_MOUTH",
        "LIPS": "OPEN_MOUTH",
        "MOUTH_OPEN": "OPEN_MOUTH",
    }
    return mapping.get(name, name)

def detect_challenge(features, challenge):
    norm_challenge = normalize_challenge(challenge)
    if norm_challenge == "TURN_LEFT":
        return analyze_head_turn(features, "LEFT", HEAD_TURN_THRESHOLD, BASELINE_SECONDS, HEAD_HOLD_FRAMES)
    if norm_challenge == "TURN_RIGHT":
        return analyze_head_turn(features, "RIGHT", HEAD_TURN_THRESHOLD, BASELINE_SECONDS, HEAD_HOLD_FRAMES)
    if norm_challenge == "TURN_UP":
        return analyze_vertical_turn(features, "UP", HEAD_TURN_THRESHOLD, BASELINE_SECONDS, HEAD_HOLD_FRAMES)
    if norm_challenge == "TURN_DOWN":
        return analyze_vertical_turn(features, "DOWN", HEAD_TURN_THRESHOLD, BASELINE_SECONDS, HEAD_HOLD_FRAMES)
    if norm_challenge == "BLINK":
        return analyze_blink(features, BLINK_THRESHOLD, BLINK_HOLD_FRAMES)
    if norm_challenge == "OPEN_MOUTH":
        return analyze_mouth_open(features, MOUTH_THRESHOLD, MOUTH_HOLD_FRAMES)
    raise ValueError(f"Unknown challenge: {challenge}")


def format_challenge_name(challenge):
    norm = normalize_challenge(challenge)
    return {
        "TURN_LEFT": "Turn Left",
        "TURN_RIGHT": "Turn Right",
        "TURN_UP": "Look Up",
        "TURN_DOWN": "Look Down",
        "BLINK": "Blink",
        "OPEN_MOUTH": "Open Mouth",
    }.get(norm, challenge)


def print_challenge_result(challenge, result):
    norm = normalize_challenge(challenge)
    status = "PASSED" if result["detected"] else "FAILED"
    print("\n" + "=" * 50)
    print("CHALLENGE RESULT")
    print("=" * 50)
    print(f"Challenge : {format_challenge_name(norm)}")
    print(f"Result    : {status}")
    print(f"Confidence: {result['score'] * 100:.1f}%")

    if norm in {"TURN_LEFT", "TURN_RIGHT", "TURN_UP", "TURN_DOWN"}:
        print(f"Movement  : {result['max_displacement']:.1f}° detected")
        print(f"Duration  : {result['longest_run']} consecutive frames")
        print(f"Tracking  : {result['valid_frames']}/{result['total_frames']} frames")
    elif norm == "OPEN_MOUTH":
        print(f"Mouth opening : {result.get('max_openness', result['max_displacement']):.3f} MAR")
        print(f"Duration      : {result['longest_run']} consecutive frames")
        print(f"Tracking      : {result['valid_frames']}/{result['total_frames']} frames")
    else:
        print(f"Blink strength: {result['max_blink']:.2f}")
        print(f"Duration      : {result['longest_run']} consecutive frames")

    print("=" * 50)

def print_mouth_opening(features):
    values = []
    timestamps = []

    for frame in features["frames"]:
        value = frame.get("mouth_open")
        if value is not None:
            timestamps.append(frame["timestamp"])
            values.append(value)

    if not values:
        print("\nNo mouth-opening data available.")
        return

    print("\n" + "=" * 50)
    print("MOUTH OPENING")
    print("=" * 50)

    print(f"Samples : {len(values)}")
    print(f"Minimum : {min(values):.4f}")
    print(f"Maximum : {max(values):.4f}")
    print(f"Mean    : {np.mean(values):.4f}")
    print(f"Median  : {np.median(values):.4f}")

    print("=" * 50)

    raw = [
        f["mouth_open_raw"]
        for f in features["frames"]
        if f["mouth_open_raw"] is not None
    ]

    smooth = [
        f["mouth_open"]
        for f in features["frames"]
        if f["mouth_open"] is not None
    ]

    print("RAW")
    print("Mean:", np.mean(raw))
    print("Max :", np.max(raw))

    print("\nSMOOTHED")
    print("Mean:", np.mean(smooth))
    print("Max :", np.max(smooth))

    plt.figure(figsize=(12, 4))
    plt.plot(timestamps, values)
    plt.xlabel("Time (seconds)")
    plt.ylabel("Mouth openness")
    plt.title("Mouth Opening Over Time")
    plt.grid(True)
    plt.show()

def print_liveness_result(movement, consistency, blink, liveness):
    score_percent = liveness * 100
    level = "HIGH" if liveness >= 0.75 else "MODERATE" if liveness >= 0.50 else "LOW"

    print("\n" + "=" * 50)
    print("VISUAL LIVENESS (EXPERIMENTAL)")
    print("=" * 50)
    print(f"Liveness : {score_percent:.1f}%")
    print(f"Level    : {level}")
    print(f"Micro-movement : {score_micro_movement(movement) * 100:.1f}%")
    print(f"Blink evidence : {blink['score'] * 100:.1f}%")
    print(f"Face tracking  : {consistency['consistency_score'] * 100:.1f}%")
    print("=" * 50)


def print_diagnostics(features, movement, consistency):
    pitches = [f["pitch"] for f in features["frames"] if f["pitch"] is not None]
    if pitches:
        print("\n[DEBUG] Pitch")
        print(f"Baseline: {pitches[0]:.2f}°")
        print(f"Minimum : {min(pitches):.2f}°")
        print(f"Maximum : {max(pitches):.2f}°")

    print("\n[DEBUG] Face consistency")
    print(f"Face coverage: {consistency['face_coverage']:.3f}")
    print(f"Landmark coverage: {consistency['landmark_coverage']:.3f}")
    print(f"Longest missing run: {consistency['longest_missing_run']} frames")

    print("\n[DEBUG] Micro-movement")
    print(f"Mean   : {movement['mean_movement']:.6f}")
    print(f"Median : {movement['median_movement']:.6f}")
    print(f"Std    : {movement['std_movement']:.6f}")
    print(f"Max    : {movement['max_movement']:.6f}")
    print(f"Samples: {movement['movement_samples']}")


if __name__ == "__main__":
    video_path = input("Enter video name: ")
    challenge_input = input("Enter challenge: ")

    features = process_video(video_path)

    challenge_result = detect_challenge(features, challenge_input)
    print_challenge_result(challenge_input, challenge_result)

    if SHOW_LIVENESS:
        movement = calculate_micro_movement(features)
        consistency = calculate_face_consistency(features)
        blink = score_blink(features)
        liveness = calculate_visual_liveness(movement, consistency, blink)
        print_liveness_result(movement, consistency, blink, liveness)
        if SHOW_MOUTH:
            print_mouth_opening(features)
        if SHOW_DIAGNOSTICS:
            print_diagnostics(features, movement, consistency)