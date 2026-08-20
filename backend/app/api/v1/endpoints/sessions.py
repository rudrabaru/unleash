import random
import uuid
from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status

from app.core.config import settings
from app.core.security import generate_challenge_token, verify_challenge_token
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

# In-memory store for session stubs (will be SQLite in Phase 2/3)
SESSION_STORE: Dict[str, Dict] = {}


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
    Validates HMAC token and launches the background analysis pipeline.
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

    # In Phase 1/2, the background task runs all 5 module calls + fusion engine
    def mock_background_pipeline(sid: str):
        # Stub result simulation
        SESSION_STORE[sid]["status"] = VerificationStatus.VERIFIED
        SESSION_STORE[sid]["confidence"] = 0.91
        SESSION_STORE[sid]["decision_reason"] = "All challenge hard gates passed. High multimodal confidence."
        SESSION_STORE[sid]["updated_at"] = datetime.now(timezone.utc)
        SESSION_STORE[sid]["signals"] = {
            "visual_liveness": DetectorResult(
                score=0.90, passed=True, reason="Natural eye movement & blink detected"
            ),
            "visual_challenge": DetectorResult(
                score=0.95, passed=True, reason="User turned head in expected direction"
            ),
            "deepfake_detection": DetectorResult(
                score=0.88, passed=True, reason="No deepfake manipulation artifacts"
            ),
            "replay_detection": DetectorResult(
                score=0.85, passed=True, reason="No screen moire patterns detected"
            ),
            "voice_authenticity": DetectorResult(
                score=0.89, passed=True, reason="Natural spectral voice distribution"
            ),
            "av_temporal_alignment": DetectorResult(
                score=0.86, passed=True, reason="Lip openness temporally aligns with spoken digits"
            )
        }

    background_tasks.add_task(mock_background_pipeline, session_id)

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
