"""
Unleash Biometric Verification - Unified Single FastAPI Application (Root)

Connects all three core pillars:
1. Visual Module: Visual Liveness & Challenge Compliance (MediaPipe) + Lip Series
2. Audio Module: Speech Gate, Phrase Compliance, Voice Authenticity, AV Temporal Alignment
3. Antispoof Module: Deepfake Detection & Replay Attack Detection
Combined with the multi-modal Fusion Engine to produce a final verdict.
"""
from __future__ import annotations

import logging
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

# Ensure backend directory is in python path
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Extend __path__ so 'from app.<submodule>' finds backend/app
__path__ = [str(BACKEND_DIR / "app")]


from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app import fusion
from app.modules.antispoof import detect_deepfake, detect_replay_attack
from app.modules.audio import process_audio_pipeline
from app.modules.frame_extraction import extract_frames
from app.modules.visual import (
    detect_visual_liveness,
    extract_landmark_features,
    extract_visual_frames,
    verify_challenge_compliance,
)
from app.modules.visual._lip_series import build_lip_series
from app.schemas.detector import DetectorResult
from app.schemas.session import VisualChallengeType

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("unleash_app")

app = FastAPI(
    title="Unleash Biometric Verification API",
    description="Unified API combining Visual Liveness, Audio Pipeline, and Antispoof Detection into a holistic verification decision.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
async def root():
    """Redirect root access directly to interactive Swagger UI documentation."""
    return RedirectResponse(url="/docs")


@app.post(
    "/verify",
    summary="Verify video against Visual, Audio, and Anti-spoofing modules",
    description="Upload a video recording (.webm, .mp4) along with the expected visual and verbal challenges to receive an itemized breakdown and overall fusion decision.",
)
async def verify_biometrics(
    video: UploadFile = File(..., description="Video recording file (.webm or .mp4)"),
    visual_challenge: VisualChallengeType = Form(
        ...,
        description="The active visual challenge prompt given to the user",
        examples=[VisualChallengeType.TURN_HEAD_LEFT],
    ),
    verbal_challenge: str = Form(
        default="walnut lantern bicycle maple trumpet",
        description="The 5 expected challenge words spoken aloud by the user",
        examples=["walnut lantern bicycle maple trumpet"],
    ),
) -> Dict[str, Any]:
    # Validate extension
    file_ext = Path(video.filename or "video.webm").suffix.lower()
    if file_ext not in (".webm", ".mp4", ".mov", ".mkv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported video format '{file_ext}'. Please upload a .webm or .mp4 file.",
        )

    # Save to a temporary file on disk
    temp_dir = BACKEND_DIR / "temp_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext, dir=temp_dir)
    temp_path = Path(temp_file.name)

    try:
        with temp_file:
            shutil.copyfileobj(video.file, temp_file)

        logger.info("Processing uploaded video '%s' (size=%d bytes)", video.filename, temp_path.stat().st_size)

        # -------------------------------------------------------------------------
        # 1. Visual Dense Frames & Landmark Extraction (Dev 2 / Visual)
        # -------------------------------------------------------------------------
        visual_res = extract_visual_frames(temp_path)
        visual_frames = visual_res.frames
        landmark_features = None

        if visual_frames:
            try:
                landmark_features = extract_landmark_features(
                    visual_frames,
                    timestamps=visual_res.timestamps,
                    original_indices=visual_res.original_indices,
                )
            except Exception as exc:
                logger.warning("Shared landmark feature extraction failed: %s", exc)

        # -------------------------------------------------------------------------
        # 2. Visual Liveness & Visual Challenge Verification (Dev 2 / Visual)
        # -------------------------------------------------------------------------
        res_visual_liveness = await detect_visual_liveness(visual_frames, features=landmark_features)
        res_visual_challenge = await verify_challenge_compliance(
            visual_frames, visual_challenge.value, features=landmark_features
        )

        # -------------------------------------------------------------------------
        # 3. Lip Series Export for Stage 4 AV Alignment (Dev 2 -> Dev 1)
        # -------------------------------------------------------------------------
        lip_openness_data = None
        if landmark_features is not None and not landmark_features.get("error"):
            try:
                lip_openness_data = build_lip_series(landmark_features, visual_res.fps)
            except Exception as exc:
                logger.warning("Lip series extraction failed: %s", exc)

        # -------------------------------------------------------------------------
        # 4. Sparse Frames for Antispoofing (Dev 3 / Antispoof)
        # -------------------------------------------------------------------------
        sparse_res = extract_frames(str(temp_path))
        sparse_frames = sparse_res.frames

        # -------------------------------------------------------------------------
        # 5. Antispoof Detectors (Deepfake & Replay) (Dev 3 / Antispoof)
        # -------------------------------------------------------------------------
        res_deepfake = await detect_deepfake(sparse_frames)
        res_replay = await detect_replay_attack(sparse_frames)

        # -------------------------------------------------------------------------
        # 6. Audio Pipeline (Stages 1-4) (Dev 1 / Audio)
        # -------------------------------------------------------------------------
        res_audio = await process_audio_pipeline(
            str(temp_path), verbal_challenge, lip_openness_data=lip_openness_data
        )

        # -------------------------------------------------------------------------
        # 7. Multi-modal Fusion Engine Evaluation
        # -------------------------------------------------------------------------
        signals: Dict[str, DetectorResult] = {
            "visual_liveness": res_visual_liveness,
            "visual_challenge": res_visual_challenge,
            "audio_pipeline": res_audio,
            "deepfake": res_deepfake,
            "replay": res_replay,
        }

        fusion_result = fusion.evaluate(signals)

        # -------------------------------------------------------------------------
        # 8. Format itemized output response
        # -------------------------------------------------------------------------
        return {
            "overall_decision": {
                "status": fusion_result.status.value,
                "confidence": fusion_result.confidence,
                "reason": fusion_result.reason,
            },
            "modules": {
                "visual": {
                    "liveness": {
                        "score": res_visual_liveness.score,
                        "passed": res_visual_liveness.passed,
                        "reason": res_visual_liveness.reason,
                        "details": res_visual_liveness.details,
                    },
                    "challenge": {
                        "challenge_type": visual_challenge.value,
                        "score": res_visual_challenge.score,
                        "passed": res_visual_challenge.passed,
                        "reason": res_visual_challenge.reason,
                        "details": res_visual_challenge.details,
                    },
                    "dense_frames_analyzed": len(visual_frames),
                    "fps": visual_res.fps,
                },
                "audio": {
                    "score": res_audio.score,
                    "passed": res_audio.passed,
                    "reason": res_audio.reason,
                    "details": res_audio.details,
                },
                "antispoof": {
                    "deepfake": {
                        "score": res_deepfake.score,
                        "passed": res_deepfake.passed,
                        "reason": res_deepfake.reason,
                        "details": res_deepfake.details,
                    },
                    "replay": {
                        "score": res_replay.score,
                        "passed": res_replay.passed,
                        "reason": res_replay.reason,
                        "details": res_replay.details,
                    },
                },
            },
        }

    finally:
        # Privacy NFR §10: Always remove temporary files
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception as e:
            logger.warning("Could not delete temporary file '%s': %s", temp_path, e)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
