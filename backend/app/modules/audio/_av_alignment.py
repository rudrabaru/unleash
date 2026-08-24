"""
Stage 4: Audio-Visual Temporal Alignment (Cross-Modal) [STUB]

This module is a placeholder stub pending the Day 19 interface design session
between Dev 1 (Audio) and Dev 2 (Visual).
In Phase 3 (Days 23-24), this will compute temporal correlation between
Whisper word-level timestamps and MediaPipe lip openness series.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.schemas.detector import DetectorResult

logger = logging.getLogger(__name__)


def run_av_alignment(
    wav_path: Path | str,
    word_timestamps: Optional[List[Dict[str, Any]]] = None,
    lip_openness_data: Optional[List[Any]] = None,
) -> DetectorResult:
    """
    Execute Stage 4 AV Temporal Alignment on audio and visual data. [STUB]

    Advisory soft gate:
      - Always returns passed=True (never gates the pipeline).
      - Returns score=None while stubbed pending Day 19 Dev 1-Dev 2 interface agreement.
      - Never returns a fake numeric score (complies with No Hardcoded Stub Values rule).
    """
    logger.info("[STUB] Stage 4 AV Temporal Alignment called.")
    return DetectorResult(
        score=None,
        passed=True,
        reason="[STUB] Stage 4 AV Temporal Alignment pending Day 19 interface agreement.",
        error=None,
        details={
            "av_alignment_score": None,
            "stub": True,
            "word_count": len(word_timestamps) if word_timestamps else 0,
        },
    )
