import logging
import secrets
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status

from app import db, housekeeping, orchestrator, quality
from app.analysis_queue import analysis_queue
from app.core.config import settings
from app.core.rate_limit import session_limiter, submit_limiter
from app.core.security import generate_challenge_token, verify_challenge_token
from app.media.probe import probe_streams
from app.modules.audio.vocabulary import CHALLENGE_VOCABULARY
from app.protocol import PROTOCOL_V1
from app.schemas.session import (
    ISSUED_VISUAL_CHALLENGES,
    ChallengePayload,
    ProtocolPayload,
    SessionCreateResponse,
    SessionResultResponse,
    SessionSubmitResponse,
    VerificationStatus,
)
from app.schemas.detector import DetectorResult

logger = logging.getLogger("unleash.sessions")

# What a caller is told when a detector failed with an internal error. The real error (which can name
# server paths or library internals) stays in the database and the logs.
PUBLIC_CHECK_ERROR = "This check could not be completed on the server."

router = APIRouter()

# Challenges must be unpredictable : use the OS CSPRNG, not the Mersenne Twister `random`.
_rng = secrets.SystemRandom()


@router.post(
    "",
    response_model=SessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(session_limiter.dependency)],
)
def create_session():
    """
    Create a new human verification session.
    Generates a random visual challenge (one of the four head actions; BLINK_TWICE is no longer
    issued, D-47) and a 5-word verbal challenge from the curated vocabulary. Signs HMAC token.
    """
    session_id = str(uuid.uuid4())

    visual_choice = _rng.choice(ISSUED_VISUAL_CHALLENGES)
    verbal_choice = " ".join(_rng.sample(CHALLENGE_VOCABULARY, 5))

    token, expires_at = generate_challenge_token(
        session_id=session_id,
        visual_challenge=visual_choice.value,
        verbal_challenge=verbal_choice,
        secret_key=settings.SECRET_KEY,
        expiry_seconds=settings.SESSION_EXPIRY_SECONDS
    )

    created_at = datetime.now(timezone.utc)
    housekeeping.prune_old_sessions(created_at)  # throttled: at most every few minutes

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
        protocol=ProtocolPayload.from_windows(PROTOCOL_V1),
        token=token,
        expires_at=expires_at,
        created_at=created_at
    )


def _check_submission(session: Optional[dict], session_id: str, token: str, media: UploadFile, content_length: Optional[int]) -> dict:
    """Everything that can refuse a submit before the session is claimed; returns the session row."""
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session {session_id} not found.")

    if session["status"] != VerificationStatus.CREATED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session {session_id} has already been submitted (status={session['status']}).",
        )

    # Refused before the session is claimed, so an oversized upload does not use up the challenge.
    if (content_length or 0) > settings.MAX_UPLOAD_BYTES or (media.size or 0) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Recording is larger than the {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )

    is_valid, error_msg = verify_challenge_token(
        token=token,
        expected_session_id=session_id,
        secret_key=settings.SECRET_KEY,
    )
    if not is_valid:
        logger.info("Refused a submit for session %s: %s", session_id, error_msg)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The session token is not valid or has expired. Please start again.",
        )
    return session


def _save_upload(media: UploadFile) -> Path:
    """Store the upload under a name of its own (several uploads may race for one session)."""
    temp_dir = Path(settings.UPLOAD_TEMP_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)
    media_path = temp_dir / f"upload_{uuid.uuid4().hex}.webm"
    try:
        with open(media_path, "wb") as buffer:
            shutil.copyfileobj(media.file, buffer)
    except OSError:
        media_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The recording could not be stored. Please try again.",
        )
    return media_path


def _refuse_unusable_recording(session: dict, media_path: Path) -> None:
    """
    Refuse, before the session is claimed, a file that cannot be a recording of this protocol. The
    session stays usable, so the person can send another recording for the same challenge.
    """
    reason = quality.upload_rejection(probe_streams(media_path, limit_seconds=quality.HARD_MAX_SECONDS))
    reason = reason or quality.submitted_too_early(
        datetime.fromisoformat(session["created_at"]), datetime.now(timezone.utc), settings.MIN_SUBMIT_SECONDS
    )
    if reason:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=reason)


@router.post(
    "/{session_id}/submit",
    response_model=SessionSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(submit_limiter.dependency)],
)
def submit_session(
    session_id: str,
    token: str = Form(...),
    media: UploadFile = File(...),
    content_length: Optional[int] = Header(default=None),
):
    """
    Submit the recorded single-blob .webm media for verification.
    Validates the HMAC token and the recording, takes a place in the analysis queue, then the
    analysis (all detectors, then fusion) runs on the queue's worker.
    """
    session = _check_submission(db.get_session(session_id), session_id, token, media, content_length)
    media_path = _save_upload(media)
    reserved = False
    try:
        _refuse_unusable_recording(session, media_path)
        # A place in the queue is taken before the session is claimed, so a busy server refuses the
        # upload without using up the challenge.
        reserved = analysis_queue.reserve()
        if not reserved:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The server is busy analysing other recordings. Please send this one again in a minute.",
                headers={"Retry-After": "30"},
            )
        # One atomic UPDATE decides which request owns the session: a concurrent second submit loses.
        if not db.claim_for_processing(session_id, datetime.now(timezone.utc)):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Session {session_id} has already been submitted.",
            )
    except HTTPException:
        if reserved:
            analysis_queue.release()
        media_path.unlink(missing_ok=True)
        raise

    visual, verbal = session["visual_challenge"], session["verbal_challenge"]
    analysis_queue.submit(lambda: _run_and_cleanup(session_id, media_path, visual, verbal))

    return SessionSubmitResponse(
        session_id=session_id,
        status=VerificationStatus.PROCESSING,
        message="Media uploaded. Verification analysis running in background.",
    )


def _run_and_cleanup(session_id: str, media_path: Path, visual_challenge: str, verbal_challenge: str) -> None:
    """Run the orchestrator, guaranteeing media cleanup post-analysis (Privacy NFR §10)."""
    try:
        orchestrator.run_verification(session_id, media_path, visual_challenge, verbal_challenge)
    except Exception:  # noqa: BLE001 - orchestrator already isolates per-detector errors;
        # this only catches a fusion/persistence-level failure so the session never hangs in PROCESSING.
        # The person did nothing wrong: they are asked to try again, and the error is logged.
        logger.exception("The analysis of session %s failed", session_id)
        db.close_session(
            session_id,
            VerificationStatus.RETRY.value,
            "The analysis could not be completed because of an error on our side. Please try again.",
            datetime.now(timezone.utc),
        )
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
        signals=_public_signals(session.get("signals")),
    )


def _public_signals(signals: Optional[Dict[str, DetectorResult]]) -> Optional[Dict[str, DetectorResult]]:
    """
    The stored results as a caller may see them: a check that failed with an internal error says so in
    plain words, and error texts inside the details are dropped. Everything stays as stored in the
    database and the logs.
    """
    if not signals:
        return signals
    public: Dict[str, DetectorResult] = {}
    for name, result in signals.items():
        details = None
        if result.details is not None:
            details = {k: v for k, v in result.details.items() if not k.endswith("_error") and k != "error"}
        if result.error is not None:
            public[name] = DetectorResult(
                score=None, passed=False, reason=PUBLIC_CHECK_ERROR, error=PUBLIC_CHECK_ERROR, details=details
            )
        else:
            public[name] = result.model_copy(update={"details": details})
    return public
