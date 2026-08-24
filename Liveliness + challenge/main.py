from config import(
    BASELINE_SECONDS,
    HEAD_TURN_THRESHOLD,
    BLINK_THRESHOLD,
    BLINK_HOLD_FRAMES
)

from calculation import (
    calculate_face_consistency,
    calculate_micro_movement,
    
)
from scoring import (
    score_blink,
    score_micro_movement,
    calculate_visual_liveness
)
from challenge_detector import (
    analyze_blink,
    analyze_head_turn,
    analyze_vertical_turn
)
from video_process import (
    process_video
)

# VIDEO_PATH = "up.mp4"
# CHALLENGE = "TURN_UP"

VIDEO_PATH = input("Enter video name: ")
CHALLENGE = input("Enter challenge: ")
SHOW_LIVENESS = True
SHOW_DIAGNOSTICS = False


def detect_challenge(features, challenge):
    if challenge == "TURN_LEFT":
        return analyze_head_turn(features, "LEFT", HEAD_TURN_THRESHOLD, BASELINE_SECONDS)
    if challenge == "TURN_RIGHT":
        return analyze_head_turn(features, "RIGHT", HEAD_TURN_THRESHOLD, BASELINE_SECONDS)
    if challenge == "TURN_UP":
        return analyze_vertical_turn(features, "UP", HEAD_TURN_THRESHOLD, BASELINE_SECONDS)
    if challenge == "TURN_DOWN":
        return analyze_vertical_turn(features, "DOWN", HEAD_TURN_THRESHOLD, BASELINE_SECONDS)
    if challenge == "BLINK":
        return analyze_blink(features, BLINK_THRESHOLD, BLINK_HOLD_FRAMES)
    raise ValueError(f"Unknown challenge: {challenge}")


def format_challenge_name(challenge):
    return {
        "TURN_LEFT": "Turn Left",
        "TURN_RIGHT": "Turn Right",
        "TURN_UP": "Look Up",
        "TURN_DOWN": "Look Down",
        "BLINK": "Blink",
    }.get(challenge, challenge)


def print_challenge_result(challenge, result):
    status = "PASSED" if result["detected"] else "FAILED"
    print("\n" + "=" * 50)
    print("CHALLENGE RESULT")
    print("=" * 50)
    print(f"Challenge : {format_challenge_name(challenge)}")
    print(f"Result    : {status}")
    print(f"Confidence: {result['score'] * 100:.1f}%")

    if challenge in {"TURN_LEFT", "TURN_RIGHT", "TURN_UP", "TURN_DOWN"}:
        print(f"Movement  : {result['max_displacement']:.1f}° detected")
        print(f"Duration  : {result['longest_run']} consecutive frames")
        print(f"Tracking  : {result['valid_frames']}/{result['total_frames']} frames")
    else:
        print(f"Blink strength: {result['max_blink']:.2f}")
        print(f"Duration      : {result['longest_run']} consecutive frames")

    print("=" * 50)


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
    features = process_video(VIDEO_PATH)

    challenge_result = detect_challenge(features, CHALLENGE)
    print_challenge_result(CHALLENGE, challenge_result)

    if SHOW_LIVENESS:
        movement = calculate_micro_movement(features)
        consistency = calculate_face_consistency(features)
        blink = score_blink(features)
        liveness = calculate_visual_liveness(movement, consistency, blink)
        print_liveness_result(movement, consistency, blink, liveness)

        if SHOW_DIAGNOSTICS:
            print_diagnostics(features, movement, consistency)