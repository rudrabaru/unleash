import secrets
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status

from app import db, orchestrator
from app.core.config import settings
from app.core.security import generate_challenge_token, verify_challenge_token
from app.modules.audio.vocabulary_builder import CHALLENGE_VOCABULARY
from app.schemas.session import (
    ChallengePayload,
    SessionCreateResponse,
    SessionResultResponse,
    SessionSubmitResponse,
    VerificationStatus,
    VisualChallengeType,
)

router = APIRouter()

# Challenges must be unpredictable (B3): use the OS CSPRNG, not the Mersenne Twister `random`.
_rng = secrets.SystemRandom()


@router.post("", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
def create_session():
    """
    Create a new human verification session.
    Generates a random visual challenge (5 types: head turns, blinks) and a 5-word
    verbal challenge (from curated, phonetically-distinct vocabulary). Signs HMAC token.
    """
    session_id = str(uuid.uuid4())

    visual_choice = _rng.choice(list(VisualChallengeType))
    verbal_choice = " ".join(_rng.sample(CHALLENGE_VOCABULARY, 5))

    token, expires_at = generate_challenge_token(
        session_id=session_id,
        visual_challenge=visual_choice.value,
        verbal_challenge=verbal_choice,
        secret_key=settings.SECRET_KEY,
        expiry_seconds=settings.SESSION_EXPIRY_SECONDS
    )

    created_at = datetime.now(timezone.utc)

    db.create_session(
        session_id=session_id,
        status=VerificationStatus.CREATED.value,
        visual_challenge=visual_choice.value,
        verbal_challenge=verbal_choice,
        created_at=created_at,
    )

    return SessionCreateResponse(
        session_id=session_id,
        challenge=ChallengePayload(visual=visual_choice, verbal=verbal_choice),
        token=token,
        expires_at=expires_at,
        created_at=created_at
    )


@router.post("/{session_id}/submit", response_model=SessionSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    token: str = Form(...),
    media: UploadFile = File(...)
):
    """
    Submit the recorded single-blob .webm media for verification.
    Validates the HMAC token and starts the analysis (all detectors, then fusion) in the background.
    """
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found."
        )

    if session["status"] != VerificationStatus.CREATED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session {session_id} has already been submitted (status={session['status']})."
        )

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

    # One atomic UPDATE decides which request owns the session: a concurrent second submit loses.
    if not db.claim_for_processing(session_id, datetime.now(timezone.utc)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session {session_id} has already been submitted.",
        )

    temp_dir = Path(settings.UPLOAD_TEMP_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)
    media_path = temp_dir / f"{session_id}.webm"

    try:
        with open(media_path, "wb") as buffer:
            shutil.copyfileobj(media.file, buffer)
    except OSError:
        db.update_session_status(session_id, VerificationStatus.FAILED.value, datetime.now(timezone.utc))
        raise

    background_tasks.add_task(
        _run_and_cleanup,
        session_id,
        media_path,
        session["visual_challenge"],
        session["verbal_challenge"],
    )

    return SessionSubmitResponse(
        session_id=session_id,
        status=VerificationStatus.PROCESSING,
        message="Media uploaded. Verification analysis running in background."
    )


def _run_and_cleanup(session_id: str, media_path: Path, visual_challenge: str, verbal_challenge: str) -> None:
    """Run the orchestrator, guaranteeing media cleanup post-analysis (Privacy NFR §10)."""
    try:
        orchestrator.run_verification(session_id, media_path, visual_challenge, verbal_challenge)
    except Exception as exc:  # noqa: BLE001 - orchestrator already isolates per-detector errors;
        # this only catches a fusion/persistence-level failure so the session never hangs in PROCESSING.
        db.update_session_status(session_id, VerificationStatus.FAILED.value, datetime.now(timezone.utc))
        raise exc
    finally:
        try:
            if media_path.exists():
                media_path.unlink()
        except OSError:
            pass


@router.get("/{session_id}", response_model=SessionResultResponse)
def get_session_result(session_id: str):
    """
    Poll session status and retrieve the final verification verdict + signal scores.
    """
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found."
        )

    return SessionResultResponse(
        session_id=session["session_id"],
        status=session["status"],
        confidence=session.get("confidence"),
        decision_reason=session.get("decision_reason", ""),
        created_at=session["created_at"],
        updated_at=session["updated_at"],
        signals=session.get("signals")
    )
