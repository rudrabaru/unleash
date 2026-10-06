from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class DetectorResult(BaseModel):
    """
    The non-negotiable 4-key shared contract for every detector module in Unleash.
    Every detector (audio, visual, antispoof) MUST return this exact schema.
    """
    score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score from 0.0 (definitely spoof/fake) to 1.0 (definitely genuine). None if errored."
    )
    passed: bool = Field(
        ...,
        description="The module's own pass/fail decision (for a must-pass check, whether it passed)."
    )
    reason: str = Field(
        ...,
        description="Human-readable explanation of the result."
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message/trace if computation failed; score must be None if error is present."
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional diagnostic telemetry and sub-signal breakdown persisted to eval store."
    )
