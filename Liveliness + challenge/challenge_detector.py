from calculation import calculate_baseline_yaw, calculate_baseline_pitch

def analyze_head_turn(
    features,
    direction,
    threshold=20.0,
    baseline_seconds=0.5,
    hold_frames=2,
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

    current_run = 0
    longest_run = 0
    max_displacement = 0.0
    valid_frames = 0

    for frame in frames:
        yaw = frame.get("yaw")
        if yaw is None:
            current_run = 0
            continue

        valid_frames += 1
        delta = yaw - baseline

        if direction == "LEFT":
            # Physical left is positive yaw
            displacement = max(0.0, delta)
            qualifies = delta >= threshold
        else:  # RIGHT
            # Physical right is negative yaw
            displacement = max(0.0, -delta)
            qualifies = delta <= -threshold

        max_displacement = max(max_displacement, displacement)

        if qualifies:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0

    score = max(0.0, min(max_displacement / threshold, 1.0))

    return {
        "detected": longest_run >= hold_frames,
        "score": score,
        "baseline_angle": baseline,
        "max_displacement": max_displacement,
        "longest_run": longest_run,
        "valid_frames": valid_frames,
        "total_frames": len(frames),
    }


def analyze_vertical_turn(
    features,
    direction,
    threshold=20.0,
    baseline_seconds=0.5,
    hold_frames=2,
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
    baseline = calculate_baseline_pitch(frames, baseline_seconds)

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

    current_run = 0
    longest_run = 0
    max_displacement = 0.0
    valid_frames = 0

    for frame in frames:
        pitch = frame.get("pitch")
        if pitch is None:
            current_run = 0
            continue

        valid_frames += 1
        displacement = pitch - baseline

        if direction == "UP":
            # Looking up produces negative displacement
            magnitude = max(0.0, -displacement)
            qualifies = displacement <= -threshold
        else:  # DOWN
            # Looking down produces positive displacement
            magnitude = max(0.0, displacement)
            qualifies = displacement >= threshold

        max_displacement = max(max_displacement, magnitude)

        if qualifies:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0

    score = max(0.0, min(max_displacement / threshold, 1.0))

    return {
        "detected": longest_run >= hold_frames,
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
    frames = features["frames"]
    current_run = 0
    longest_run = 0
    max_blink = 0.0
    valid_frames = 0

    for frame in frames:
        left = frame.get("blink_left")
        right = frame.get("blink_right")

        if left is None or right is None:
            current_run = 0
            continue

        valid_frames += 1
        value = (left + right) / 2.0
        max_blink = max(max_blink, value)

        if value >= threshold:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0

    score = max(0.0, min(max_blink / threshold, 1.0)) if threshold > 0 else 0.0

    return {
        "detected": longest_run >= hold_frames,
        "score": score,
        "max_blink": max_blink,
        "max_displacement": max_blink,
        "longest_run": longest_run,
        "valid_frames": valid_frames,
        "total_frames": len(frames),
    }


def analyze_mouth_open(
    features,
    threshold=0.35,
    hold_frames=2,
):
    """
    Detect mouth/lip opening using Mouth Aspect Ratio (MAR).
    """
    frames = features["frames"]
    current_run = 0
    longest_run = 0
    max_open = 0.0
    valid_frames = 0

    for frame in frames:
        mouth = frame.get("mouth_open")
        if mouth is None:
            current_run = 0
            continue

        valid_frames += 1
        max_open = max(max_open, mouth)

        if mouth >= threshold:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0

    score = max(0.0, min(max_open / threshold, 1.0)) if threshold > 0 else 0.0

    return {
        "detected": longest_run >= hold_frames,
        "score": score,
        "max_openness": max_open,
        "max_displacement": max_open,
        "longest_run": longest_run,
        "valid_frames": valid_frames,
        "total_frames": len(frames),
    }
