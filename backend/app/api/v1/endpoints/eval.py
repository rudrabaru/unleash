from typing import List
from fastapi import APIRouter

from app.api.v1.endpoints.sessions import SESSION_STORE
from app.schemas.session import SessionResultResponse

router = APIRouter()


@router.get("/sessions", response_model=List[SessionResultResponse])
async def list_evaluation_sessions():
    """
    Evaluation dashboard endpoint to fetch all historical verification sessions
    and their per-signal breakdown for TAR/FAR analysis.
    (Owned by Dev 3)
    """
    return [
        SessionResultResponse(
            session_id=s["session_id"],
            status=s["status"],
            confidence=s.get("confidence"),
            decision_reason=s.get("decision_reason", ""),
            created_at=s["created_at"],
            updated_at=s["updated_at"],
            signals=s.get("signals")
        )
        for s in SESSION_STORE.values()
    ]
