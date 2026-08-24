from challenge_detector import analyze_blink
from config import BLINK_HOLD_FRAMES , BLINK_THRESHOLD

def score_micro_movement(
    movement,
    low_threshold=0.001,
    high_threshold=0.005,
):
    """
    Convert micro-movement into a 0-1 score.

    Below low_threshold:
        treated as essentially static.

    Above high_threshold:
        treated as sufficient natural movement.

    Between them:
        linearly interpolated.
    """

    mean_movement = movement["mean_movement"]

    if mean_movement <= low_threshold:
        return 0.0

    if mean_movement >= high_threshold:
        return 1.0

    score = (
        (mean_movement - low_threshold)
        / (high_threshold - low_threshold)
    )

    return max(0.0, min(score, 1.0))

def score_blink(features):
    """
    Blink contributes supporting evidence of liveness.

    It is intentionally not mandatory.
    """

    result = analyze_blink(
        features,
        threshold=BLINK_THRESHOLD,
        hold_frames=BLINK_HOLD_FRAMES
    )

    return {
        "detected": result["detected"],
        "score": result["score"],
        "max_blink": result["max_blink"],
    }
def calculate_visual_liveness(
    movement,
    consistency,
    blink,
):
    """
    Calculate the initial Visual Liveness score.

    Micro-movement is the primary signal.
    Face consistency acts as a tracking-quality gate.
    Blink provides supporting evidence.

    Returns a score from 0 to 1.
    """

    movement_score = score_micro_movement(
        movement
    )

    consistency_score = consistency[
        "consistency_score"
    ]

    blink_score = blink["score"]

    # --------------------------------------------------
    # Primary liveness evidence
    # --------------------------------------------------

    # Micro-movement carries the most weight.
    #
    # Blink is supporting evidence rather than a
    # requirement because a live person may not blink
    # during a short recording.

    visual_score = (
        0.70 * movement_score
        +
        0.20 * blink_score
        +
        0.10 * consistency_score
    )

    # --------------------------------------------------
    # Tracking-quality gate
    # --------------------------------------------------

    if consistency_score < 0.5:
        visual_score *= consistency_score

    return max(
        0.0,
        min(visual_score, 1.0)
    )