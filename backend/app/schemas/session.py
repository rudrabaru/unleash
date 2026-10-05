from datetime import datetime
from enum import Enum
from typing import Dict, Optional
from pydantic import BaseModel, Field

from app.schemas.detector import DetectorResult


class VisualChallengeType(str, Enum):
    TURN_HEAD_LEFT = "TURN_HEAD_LEFT"
    TURN_HEAD_RIGHT = "TURN_HEAD_RIGHT"
    LOOK_UP = "LOOK_UP"
    LOOK_DOWN = "LOOK_DOWN"
    BLINK_TWICE = "BLINK_TWICE"


class VerificationStatus(str, Enum):
    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    VERIFIED = "VERIFIED"
    SUSPICIOUS = "SUSPICIOUS"
    FAILED = "FAILED"


class ChallengePayload(BaseModel):
    visual: VisualChallengeType = Field(..., description="Visual action requested from user")
    verbal: str = Field(..., description="5 space-separated words the user must speak in order")


class SessionCreateResponse(BaseModel):
    session_id: str
    challenge: ChallengePayload
    token: str
    expires_at: int
    created_at: datetime


class SessionSubmitResponse(BaseModel):
    session_id: str
    status: VerificationStatus = VerificationStatus.PROCESSING
    message: str = "Media uploaded successfully. Analysis in progress."


class SessionResultResponse(BaseModel):
    session_id: str
    status: VerificationStatus
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    decision_reason: str
    created_at: datetime
    updated_at: datetime
    signals: Optional[Dict[str, DetectorResult]] = Field(
        default=None,
        description="Individual results for each of the 6 detection signals"
    )


class VerifyResponse(BaseModel):
    """Result of the development-only POST /verify demo: every detector's result and the verdict."""
    status: VerificationStatus
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    reason: str
    signals: Dict[str, DetectorResult]
    timings: Dict[str, float] = Field(description="Seconds spent in each analysis step")
