from datetime import datetime
from enum import Enum
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from app.protocol import PhaseWindows
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
    # The recording could not be judged (capture problem or an error on our side): try again with a
    # new challenge. Neither an acceptance nor evidence against the person.
    RETRY = "RETRY"


class ChallengePayload(BaseModel):
    visual: VisualChallengeType = Field(..., description="Visual action requested from user")
    verbal: str = Field(..., description="5 space-separated words the user must speak in order")


class PhaseWindow(BaseModel):
    name: Literal["read", "speak", "act"]
    start: float = Field(..., description="Seconds from the start of the recording")
    end: float = Field(..., description="Seconds from the start of the recording")


class ProtocolPayload(BaseModel):
    """How the recording is divided into phases (see app/protocol.py). The browser draws its timers from this."""
    version: int
    total_seconds: float
    min_recording_seconds: float
    max_recording_seconds: float
    phases: List[PhaseWindow]

    @classmethod
    def from_windows(cls, windows: PhaseWindows) -> "ProtocolPayload":
        return cls(
            version=windows.version,
            total_seconds=windows.total_seconds,
            min_recording_seconds=windows.min_recording_seconds,
            max_recording_seconds=windows.max_recording_seconds,
            phases=[PhaseWindow(name=p.name, start=p.start, end=p.end) for p in windows.phases],
        )


class SessionCreateResponse(BaseModel):
    session_id: str
    challenge: ChallengePayload
    protocol: ProtocolPayload
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
