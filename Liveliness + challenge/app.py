import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from calculation import calculate_face_consistency, calculate_micro_movement
from challenge_detector import (
    analyze_blink,
    analyze_head_turn,
    analyze_mouth_open,
    analyze_vertical_turn,
)
from config import (
    BASELINE_SECONDS,
    BLINK_HOLD_FRAMES,
    BLINK_THRESHOLD,
    HEAD_HOLD_FRAMES,
    HEAD_TURN_THRESHOLD,
    MOUTH_HOLD_FRAMES,
    MOUTH_THRESHOLD,
)
from scoring import (
    calculate_visual_liveness,
    score_blink,
    score_micro_movement,
)
from video_process import process_video

app = FastAPI(
    title="Liveness & Challenge Verification API",
    description="Analyze video recordings for facial liveness and challenge execution.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPPORTED_CHALLENGES = {
    "TURN_LEFT": "Turn Head Left",
    "TURN_RIGHT": "Turn Head Right",
    "TURN_UP": "Look Up",
    "TURN_DOWN": "Look Down",
    "BLINK": "Blink Eyes",
    "OPEN_MOUTH": "Open Mouth / Lips",
}


def normalize_challenge(challenge_str: str) -> str:
    cleaned = challenge_str.strip().upper().replace(" ", "_")
    alias_map = {
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
    return alias_map.get(cleaned, cleaned)


def build_reason_text(challenge: str, result: dict) -> str:
    passed = result["detected"]
    longest_run = result.get("longest_run", 0)

    if challenge in ("TURN_LEFT", "TURN_RIGHT"):
        direction = "Left" if challenge == "TURN_LEFT" else "Right"
        disp = result.get("max_displacement", 0.0)
        if passed:
            return (
                f"Challenge Turn {direction} passed: reached {disp:.1f}° displacement "
                f"held for {longest_run} consecutive frames (threshold: {HEAD_TURN_THRESHOLD}°, "
                f"required hold: {HEAD_HOLD_FRAMES} frames)."
            )
        return (
            f"Challenge Turn {direction} failed: maximum displacement was {disp:.1f}° "
            f"(threshold: {HEAD_TURN_THRESHOLD}°)."
        )

    if challenge in ("TURN_UP", "TURN_DOWN"):
        direction = "Up" if challenge == "TURN_UP" else "Down"
        disp = result.get("max_displacement", 0.0)
        if passed:
            return (
                f"Challenge Look {direction} passed: reached {disp:.1f}° displacement "
                f"held for {longest_run} consecutive frames (threshold: {HEAD_TURN_THRESHOLD}°, "
                f"required hold: {HEAD_HOLD_FRAMES} frames)."
            )
        return (
            f"Challenge Look {direction} failed: maximum displacement was {disp:.1f}° "
            f"(threshold: {HEAD_TURN_THRESHOLD}°)."
        )

    if challenge == "BLINK":
        max_blink = result.get("max_blink", 0.0)
        if passed:
            return (
                f"Challenge Blink passed: eye closure reached {max_blink:.2f} "
                f"held for {longest_run} consecutive frames (threshold: {BLINK_THRESHOLD}, "
                f"required hold: {BLINK_HOLD_FRAMES} frames)."
            )
        return (
            f"Challenge Blink failed: maximum eye closure was {max_blink:.2f} "
            f"(threshold: {BLINK_THRESHOLD})."
        )

    if challenge == "OPEN_MOUTH":
        max_open = result.get("max_openness", result.get("max_displacement", 0.0))
        if passed:
            return (
                f"Challenge Open Mouth passed: mouth openness reached {max_open:.3f} MAR "
                f"held for {longest_run} consecutive frames (threshold: {MOUTH_THRESHOLD}, "
                f"required hold: {MOUTH_HOLD_FRAMES} frames)."
            )
        return (
            f"Challenge Open Mouth failed: maximum openness was {max_open:.3f} MAR "
            f"(threshold: {MOUTH_THRESHOLD})."
        )

    return "Challenge verification finished."


class AnalysisResponse(BaseModel):
    score: float = Field(..., description="Final score of the challenge (0.0 to 1.0)")
    pass_fail: str = Field(..., alias="pass/fail", description="Challenge outcome: PASS or FAIL")
    reason: str = Field(..., description="Explanation of why the challenge passed or failed")
    errors: Optional[List[str]] = Field(default=None, description="List of errors encountered, if any")
    details: Dict[str, Any] = Field(..., description="Detailed metrics including liveness score")

    class Config:
        populate_by_name = True


@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/docs")


@app.get("/challenges", response_model=Dict[str, str])
def get_challenges():
    return SUPPORTED_CHALLENGES


@app.post("/analyze", response_model=AnalysisResponse)
@app.post("/api/analyze", response_model=AnalysisResponse, include_in_schema=False)
async def analyze_video(
    file: UploadFile = File(..., description="Video file (.mp4, .avi, .mov, etc.)"),
    challenge: str = Form(..., description="Challenge name: TURN_LEFT, TURN_RIGHT, TURN_UP, TURN_DOWN, BLINK, OPEN_MOUTH"),
):
    if not file or not file.filename:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "score": 0.0,
                "pass/fail": "FAIL",
                "reason": "No video file was uploaded.",
                "errors": ["File upload is required."],
                "details": {"liveness_score": 0.0},
            },
        )

    norm_challenge = normalize_challenge(challenge)
    if norm_challenge not in SUPPORTED_CHALLENGES:
        valid_options = ", ".join(SUPPORTED_CHALLENGES.keys())
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "score": 0.0,
                "pass/fail": "FAIL",
                "reason": f"Unsupported challenge '{challenge}'.",
                "errors": [f"Invalid challenge. Supported challenges: {valid_options}"],
                "details": {"liveness_score": 0.0},
            },
        )

    suffix = Path(file.filename).suffix or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        features = process_video(tmp_path)
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "score": 0.0,
                "pass/fail": "FAIL",
                "reason": "Video processing failed.",
                "errors": [str(e)],
                "details": {"liveness_score": 0.0},
            },
        )
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    frames = features.get("frames", [])
    if not frames:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "score": 0.0,
                "pass/fail": "FAIL",
                "reason": "No frames could be extracted from the video.",
                "errors": ["Empty or corrupted video file."],
                "details": {"liveness_score": 0.0},
            },
        )

    # 1. Challenge Execution
    if norm_challenge == "TURN_LEFT":
        challenge_res = analyze_head_turn(
            features, "LEFT", HEAD_TURN_THRESHOLD, BASELINE_SECONDS, HEAD_HOLD_FRAMES
        )
    elif norm_challenge == "TURN_RIGHT":
        challenge_res = analyze_head_turn(
            features, "RIGHT", HEAD_TURN_THRESHOLD, BASELINE_SECONDS, HEAD_HOLD_FRAMES
        )
    elif norm_challenge == "TURN_UP":
        challenge_res = analyze_vertical_turn(
            features, "UP", HEAD_TURN_THRESHOLD, BASELINE_SECONDS, HEAD_HOLD_FRAMES
        )
    elif norm_challenge == "TURN_DOWN":
        challenge_res = analyze_vertical_turn(
            features, "DOWN", HEAD_TURN_THRESHOLD, BASELINE_SECONDS, HEAD_HOLD_FRAMES
        )
    elif norm_challenge == "BLINK":
        challenge_res = analyze_blink(features, BLINK_THRESHOLD, BLINK_HOLD_FRAMES)
    elif norm_challenge == "OPEN_MOUTH":
        challenge_res = analyze_mouth_open(features, MOUTH_THRESHOLD, MOUTH_HOLD_FRAMES)
    else:
        challenge_res = {"detected": False, "score": 0.0}

    # 2. Liveness Evaluation
    movement = calculate_micro_movement(features)
    consistency = calculate_face_consistency(features)
    blink = score_blink(features)
    visual_liveness = calculate_visual_liveness(movement, consistency, blink)

    liveness_level = (
        "HIGH"
        if visual_liveness >= 0.75
        else "MODERATE"
        if visual_liveness >= 0.50
        else "LOW"
    )

    passed = bool(challenge_res.get("detected", False))
    challenge_score = round(float(challenge_res.get("score", 0.0)), 4)
    reason = build_reason_text(norm_challenge, challenge_res)

    details = {
        "liveness_score": round(float(visual_liveness), 4),
        "liveness_level": liveness_level,
        "micro_movement_score": round(float(score_micro_movement(movement)), 4),
        "blink_evidence_score": round(float(blink.get("score", 0.0)), 4),
        "face_consistency_score": round(float(consistency.get("consistency_score", 0.0)), 4),
        "challenge_key": norm_challenge,
        "challenge_name": SUPPORTED_CHALLENGES.get(norm_challenge, norm_challenge),
        "challenge_detected": passed,
        "longest_consecutive_run": challenge_res.get("longest_run", 0),
        "max_displacement": round(float(challenge_res.get("max_displacement", 0.0)), 4),
        "valid_frames": challenge_res.get("valid_frames", len(frames)),
        "total_frames": challenge_res.get("total_frames", len(frames)),
        "video_metadata": {
            "fps": round(float(features.get("fps", 0.0)), 2),
            "frame_count": features.get("frame_count", len(frames)),
            "duration_seconds": round(float(features.get("duration", 0.0)), 2),
        },
    }

    return {
        "score": challenge_score,
        "pass/fail": "PASS" if passed else "FAIL",
        "reason": reason,
        "errors": None,
        "details": details,
    }


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
