"""
Stage 4: Audio-Visual Temporal Alignment (Cross-Modal) [REAL]

Interface finalized solo by Dev 1 (Dev 2 unavailable, user-authorized) in
`.claude/context/audio-pipeline/av-alignment-interface.md` — read that file for the exact
lip-series/word-timestamp shapes and the full design rationale before changing this module.

Advisory only: `passed` is always True regardless of score. Never fabricates a numeric
score (J5) — missing or non-overlapping input degrades to `score=None` with a
`degraded_reason`, not a plausible-looking number. Calibration status: [UNCALIBRATED] —
see the interface doc and stage-specifications.md.
"""
from __future__ import annotations

import logging
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.schemas.detector import DetectorResult

logger = logging.getLogger(__name__)

# ±300ms tolerance, already agreed in the project plan (Section 5.5).
ALIGNMENT_TOLERANCE_SECONDS = 0.3
# Fraction of a word's overlapping frames that must show elevated lip opening for that
# word to count as "aligned". [UNCALIBRATED] initial guess.
WORD_OPEN_FRACTION_THRESHOLD = 0.30
# Dynamic per-session "open" threshold = median(series) + OPEN_THRESHOLD_STDEV_MULT * stdev(series),
# floored at OPEN_THRESHOLD_MIN_MARGIN above the median. [UNCALIBRATED] initial guess.
OPEN_THRESHOLD_STDEV_MULT = 0.5
OPEN_THRESHOLD_MIN_MARGIN = 0.02


def _degraded_result(reason: str, word_count: int) -> DetectorResult:
    return DetectorResult(
        score=None,
        passed=True,
        reason=reason,
        error=None,
        details={
            "av_alignment_score": None,
            "word_count": word_count,
            "degraded": True,
            "degraded_reason": reason,
        },
    )


def _open_threshold(ratios: List[float]) -> float:
    median = statistics.median(ratios)
    stdev = statistics.stdev(ratios) if len(ratios) > 1 else 0.0
    return median + max(OPEN_THRESHOLD_MIN_MARGIN, OPEN_THRESHOLD_STDEV_MULT * stdev)


def _word_is_aligned(word: Dict[str, Any], frame_index_to_ratio: Dict[int, float], fps: float, open_threshold: float) -> Optional[bool]:
    window_start = word["start"] - ALIGNMENT_TOLERANCE_SECONDS
    window_end = word["end"] + ALIGNMENT_TOLERANCE_SECONDS
    start_index = max(0, int(window_start * fps))
    end_index = int(window_end * fps) + 1

    overlapping_ratios = [
        ratio for index, ratio in frame_index_to_ratio.items() if start_index <= index <= end_index
    ]
    if not overlapping_ratios:
        return None

    open_fraction = sum(1 for ratio in overlapping_ratios if ratio >= open_threshold) / len(overlapping_ratios)
    return open_fraction >= WORD_OPEN_FRACTION_THRESHOLD


def run_av_alignment(
    wav_path: Path | str,
    word_timestamps: Optional[List[Dict[str, Any]]] = None,
    lip_openness_data: Optional[Dict[str, Any]] = None,
) -> DetectorResult:
    """
    Execute Stage 4 AV Temporal Alignment.

    `lip_openness_data` shape: {"fps": float, "series": [{"frame_index": int,
    "lip_openness_ratio": float}, ...]}, per av-alignment-interface.md. `word_timestamps`
    shape: [{"word": str, "start": float, "end": float, "probability": float}, ...].
    """
    word_count = len(word_timestamps) if word_timestamps else 0

    if not word_timestamps:
        return _degraded_result("No word timestamps available for AV alignment.", word_count)

    if not lip_openness_data or not lip_openness_data.get("series"):
        return _degraded_result("No lip openness data available for AV alignment.", word_count)

    fps = lip_openness_data.get("fps")
    series = lip_openness_data["series"]
    if not fps or fps <= 0:
        return _degraded_result("Lip openness data has no valid fps.", word_count)

    try:
        frame_index_to_ratio = {
            entry["frame_index"]: entry["lip_openness_ratio"]
            for entry in series
            if entry.get("lip_openness_ratio") is not None
        }
        if not frame_index_to_ratio:
            return _degraded_result("Lip openness series contained no usable ratios.", word_count)

        open_threshold = _open_threshold(list(frame_index_to_ratio.values()))

        word_results = [
            _word_is_aligned(word, frame_index_to_ratio, fps, open_threshold)
            for word in word_timestamps
        ]
        judged = [result for result in word_results if result is not None]

        if not judged:
            return _degraded_result(
                "No spoken word overlapped any sampled video frame (fps/timing mismatch).",
                word_count,
            )

        score = round(sum(1 for result in judged if result) / len(judged), 4)
        reason = (
            f"AV alignment: {sum(1 for r in judged if r)}/{len(judged)} words showed "
            f"corresponding lip movement (of {word_count} total words; "
            f"{word_count - len(judged)} had no overlapping frames)."
        )

        return DetectorResult(
            score=score,
            passed=True,
            reason=reason,
            error=None,
            details={
                "av_alignment_score": score,
                "word_count": word_count,
                "words_judged": len(judged),
                "words_aligned": sum(1 for r in judged if r),
                "open_threshold": round(open_threshold, 4),
                "degraded": False,
            },
        )
    except Exception as exc:  # noqa: BLE001 - a detector must never raise
        logger.exception("Unexpected error in run_av_alignment")
        return DetectorResult(
            score=None,
            passed=True,
            reason=f"AV alignment failed unexpectedly: {type(exc).__name__}: {exc}",
            error=str(exc),
            details={"av_alignment_score": None, "word_count": word_count, "degraded": True},
        )
