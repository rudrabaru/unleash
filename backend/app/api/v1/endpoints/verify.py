"""
Development-only module demo: upload one recording, get every detector's result and the
fused verdict back, without creating a session or storing anything.
"""
import logging
import shutil
import uuid
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app import orchestrator
from app.core.config import settings
from app.schemas.session import VerifyResponse, VisualChallengeType

logger = logging.getLogger("unleash.verify")

router = APIRouter()

ALLOWED_SUFFIXES = (".webm", ".mp4", ".mov", ".mkv")


@router.post("", response_model=VerifyResponse)
async def verify_clip(
    video: UploadFile = File(..., description="Recording with video and audio (.webm, .mp4, .mov or .mkv)"),
    visual_challenge: VisualChallengeType = Form(..., description="The visual action the person was asked to do"),
    verbal_challenge: str = Form(..., description="The 5 words the person was asked to say, space separated"),
) -> VerifyResponse:
    if settings.ENVIRONMENT != "development":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    suffix = Path(video.filename or "clip.webm").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported video format '{suffix}'. Use one of: {', '.join(ALLOWED_SUFFIXES)}.",
        )

    temp_dir = Path(settings.UPLOAD_TEMP_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)
    media_path = temp_dir / f"verify_{uuid.uuid4().hex}{suffix}"
    try:
        with open(media_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)
        analysis = await orchestrator.analyze_media(media_path, visual_challenge.value, verbal_challenge)
    finally:
        try:
            media_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete temporary file %s", media_path)

    signals: Dict[str, object] = analysis.signals
    return VerifyResponse(
        status=analysis.fusion.status,
        confidence=analysis.fusion.confidence,
        reason=analysis.fusion.reason,
        signals=signals,
        timings=analysis.timings,
    )
