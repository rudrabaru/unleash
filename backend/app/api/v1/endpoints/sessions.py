import random
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status

from app.core.config import settings
from app.core.security import generate_challenge_token, verify_challenge_token
from app.modules.audio import process_audio_pipeline
from app.schemas.detector import DetectorResult
from app.schemas.session import (
    ChallengePayload,
    SessionCreateResponse,
    SessionResultResponse,
    SessionSubmitResponse,
    VerificationStatus,
    VisualChallengeType,
)

router = APIRouter()

# In-memory store for session records (will be SQLite in Phase 2/3)
SESSION_STORE: Dict[str, Dict] = {}


async def _run_background_pipeline(sid: str, media_file_path: Path, challenge_phrase: str):
    """
    Execute real audio pipeline and update session verification status.
    Guarantees cleanup of temporary uploaded media file post-analysis (Privacy NFR §10).
    """
    try:
        audio_result = await process_audio_pipeline(str(media_file_path), challenge_phrase)
        now = datetime.now(timezone.utc)
        if sid not in SESSION_STORE:
            return

        SESSION_STORE[sid]["updated_at"] = now
        SESSION_STORE[sid]["signals"] = {
            "audio_pipeline": audio_result
        }

        if audio_result.passed:
            SESSION_STORE[sid]["status"] = VerificationStatus.VERIFIED
            SESSION_STORE[sid]["confidence"] = audio_result.score
            SESSION_STORE[sid]["decision_reason"] = f"Audio challenge verified: {audio_result.reason}"
        else:
            SESSION_STORE[sid]["status"] = VerificationStatus.FAILED
            SESSION_STORE[sid]["confidence"] = audio_result.score
            SESSION_STORE[sid]["decision_reason"] = f"Verification failed: {audio_result.reason}"
    except Exception as e:
        if sid in SESSION_STORE:
            SESSION_STORE[sid]["status"] = VerificationStatus.FAILED
            SESSION_STORE[sid]["confidence"] = None
            SESSION_STORE[sid]["decision_reason"] = f"Verification pipeline error: {e}"
            SESSION_STORE[sid]["updated_at"] = datetime.now(timezone.utc)
    finally:
        # Privacy NFR §10: Delete raw uploaded media blob after analysis completes
        try:
            if media_file_path.exists():
                media_file_path.unlink()
        except OSError:
            pass


@router.post("", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_session():
    """
    Create a new human verification session.
    Generates random visual & verbal challenges and signs an HMAC token.
    (Owned by Dev 2 in integration)
    """
    session_id = str(uuid.uuid4())
    
    # 1. Random visual challenge
    visual_choice = random.choice(list(VisualChallengeType))
    
    # 2. Random 3-digit verbal challenge (100 - 999)
    verbal_choice = str(random.randint(100, 999))
    
    # 3. Generate HMAC token with expiry
    token, expires_at = generate_challenge_token(
        session_id=session_id,
        visual_challenge=visual_choice.value,
        verbal_challenge=verbal_choice,
        secret_key=settings.SECRET_KEY,
        expiry_seconds=settings.SESSION_EXPIRY_SECONDS
    )
    
    created_at = datetime.now(timezone.utc)
    
    SESSION_STORE[session_id] = {
        "session_id": session_id,
        "status": VerificationStatus.CREATED,
        "challenge": {
            "visual": visual_choice,
            "verbal": verbal_choice
        },
        "token": token,
        "expires_at": expires_at,
        "created_at": created_at,
        "updated_at": created_at,
        "confidence": None,
        "decision_reason": "Session created. Awaiting media upload.",
        "signals": {}
    }
    
    return SessionCreateResponse(
        session_id=session_id,
        challenge=ChallengePayload(visual=visual_choice, verbal=verbal_choice),
        token=token,
        expires_at=expires_at,
        created_at=created_at
    )


@router.post("/{session_id}/submit", response_model=SessionSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    token: str = Form(...),
    media: UploadFile = File(...)
):
    """
    Submit the recorded single-blob .webm media for verification.
    Validates HMAC token and launches the real background analysis pipeline.
    (Orchestration lead: Dev 3)
    """
    if session_id not in SESSION_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found."
        )

    # Validate HMAC token
    is_valid, error_msg = verify_challenge_token(
        token=token,
        expected_session_id=session_id,
        secret_key=settings.SECRET_KEY
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Security verification failed: {error_msg}"
        )

    SESSION_STORE[session_id]["status"] = VerificationStatus.PROCESSING
    SESSION_STORE[session_id]["updated_at"] = datetime.now(timezone.utc)

    # Save uploaded media file to temporary upload directory
    temp_dir = Path(settings.UPLOAD_TEMP_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)
    media_path = temp_dir / f"{session_id}.webm"

    with open(media_path, "wb") as buffer:
        shutil.copyfileobj(media.file, buffer)

    verbal_challenge = str(SESSION_STORE[session_id]["challenge"]["verbal"])
    background_tasks.add_task(_run_background_pipeline, session_id, media_path, verbal_challenge)

    return SessionSubmitResponse(
        session_id=session_id,
        status=VerificationStatus.PROCESSING,
        message="Media uploaded. Verification analysis running in background."
    )


@router.get("/{session_id}", response_model=SessionResultResponse)
async def get_session_result(session_id: str):
    """
    Poll session status and retrieve the final verification verdict + 6-signal scores.
    """
    if session_id not in SESSION_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found."
        )

    session = SESSION_STORE[session_id]
    return SessionResultResponse(
        session_id=session["session_id"],
        status=session["status"],
        confidence=session.get("confidence"),
        decision_reason=session.get("decision_reason", ""),
        created_at=session["created_at"],
        updated_at=session["updated_at"],
        signals=session.get("signals")
    )
