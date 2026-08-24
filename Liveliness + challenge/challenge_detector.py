from calculation import calculate_baseline_yaw
import statistics

def analyze_head_turn(
    features,
    direction,
    threshold=20.0,
    baseline_seconds=0.5,
):
    direction = direction.upper()

    if direction not in ("LEFT", "RIGHT"):
        raise ValueError("Direction must be LEFT or RIGHT")

    frames = features["frames"]
    baseline = calculate_baseline_yaw(frames, baseline_seconds)

    if baseline is None:
        return {
            "detected": False,
            "score": 0.0,
            "baseline_angle": None,
            "max_displacement": 0.0,
            "longest_run": 0,
            "valid_frames": 0,
            "total_frames": len(frames),
        }

    deltas = [
        frame["yaw"] - baseline
        for frame in frames
        if frame["yaw"] is not None
    ]

    if direction == "LEFT":
        max_displacement = max(deltas, default=0.0)
        qualifies = lambda d: d >= threshold
    else:
        max_displacement = abs(min(deltas, default=0.0))
        qualifies = lambda d: d <= -threshold

    current_run = 0
    longest_run = 0

    for frame in frames:
        yaw = frame["yaw"]

        if yaw is None:
            current_run = 0
            continue

        if qualifies(yaw - baseline):
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0

    score = min(max_displacement / threshold, 1.0)

    return {
        "detected": longest_run > 0,
        "score": score,
        "baseline_angle": baseline,
        "max_displacement": max_displacement,
        "longest_run": longest_run,
        "valid_frames": len(deltas),
        "total_frames": len(frames),
    }

def analyze_vertical_turn(
    features,
    direction,
    threshold=20.0,
    baseline_seconds=0.5,
):
    """
    Detect UP/DOWN head movement using pitch.

    Validated convention:
        UP   -> negative pitch displacement
        DOWN -> positive pitch displacement
    """

    direction = direction.upper()

    if direction not in ("UP", "DOWN"):
        raise ValueError("Direction must be UP or DOWN")

    frames = features["frames"]

    baseline_values = [
        frame["pitch"]
        for frame in frames
        if (
            frame["pitch"] is not None
            and frame["timestamp"] <= baseline_seconds
        )
    ]

    if not baseline_values:
        return {
            "detected": False,
            "score": 0.0,
            "baseline_angle": None,
            "max_displacement": 0.0,
            "longest_run": 0,
            "valid_frames": 0,
            "total_frames": len(frames),
        }

    baseline = statistics.median(baseline_values)

    current_run = 0
    longest_run = 0
    max_displacement = 0.0
    valid_frames = 0

    for frame in frames:

        pitch = frame["pitch"]

        if pitch is None:
            current_run = 0
            continue

        valid_frames += 1

        displacement = pitch - baseline

        if direction == "UP":
            qualifies = displacement <= -threshold
            magnitude = abs(displacement)

        else:  # DOWN
            qualifies = displacement >= threshold
            magnitude = displacement

        max_displacement = max(
            max_displacement,
            magnitude
        )

        if qualifies:
            current_run += 1
            longest_run = max(
                longest_run,
                current_run
            )
        else:
            current_run = 0

    score = min(
        max_displacement / threshold,
        1.0
    )

    return {
        "detected": longest_run > 0,
        "score": score,
        "baseline_angle": baseline,
        "max_displacement": max_displacement,
        "longest_run": longest_run,
        "valid_frames": valid_frames,
        "total_frames": len(frames),
    }

def analyze_blink(
    features,
    threshold=0.5,
    hold_frames=2,
):
    values = []

    for frame in features["frames"]:
        left = frame["blink_left"]
        right = frame["blink_right"]

        if left is not None and right is not None:
            values.append((left + right) / 2.0)

    if not values:
        return {
            "detected": False,
            "score": 0.0,
            "max_blink": 0.0,
            "longest_run": 0,
        }

    max_blink = max(values)
    current_run = 0
    longest_run = 0

    for value in values:
        if value >= threshold:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0

        longest_run = max(longest_run, current_run)

    return {
        "detected": longest_run >= hold_frames,
        "score": min(max_blink / threshold, 1.0),
        "max_blink": max_blink,
        "longest_run": longest_run,
    }
