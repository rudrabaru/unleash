"""
Stage 4: Audio-Visual Temporal Alignment (Cross-Modal) [REAL]

Interface finalized solo by Dev 1 (Dev 2 unavailable, user-authorized) in
`.claude/context/audio-pipeline/av-alignment-interface.md` — read that file for the exact
lip-series/word-timestamp shapes and the full design rationale before changing this module.

Timing comes ONLY from each lip sample's own `time_seconds` (decision B4/D-19). The old
`frame_index / fps` conversion is gone: browser `.webm` reports a bogus 1000 fps and the
indices count subsampled frames, so it either found no overlap or, worse, produced a
plausible-looking but wrong score. A series without usable `time_seconds` now degrades to
`score=None` (J5).

Advisory only: `passed` is always True regardless of score. Never fabricates a numeric
score (J5) — missing or non-overlapping input degrades to `score=None` with a
`degraded_reason`, not a plausible-looking number. Calibration status: [UNCALIBRATED] —
see the interface doc and stage-specifications.md.
"""
from __future__ import annotations

import logging
import math
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.detector import DetectorResult

logger = logging.getLogger(__name__)

# ±300ms tolerance, already agreed in the project plan (Section 5.5).
ALIGNMENT_TOLERANCE_SECONDS = 0.3
# Fraction of a word's overlapping samples that must show elevated lip opening for that
# word to count as "aligned". [UNCALIBRATED] initial guess.
WORD_OPEN_FRACTION_THRESHOLD = 0.30
# Dynamic per-session "open" threshold = median(series) + OPEN_THRESHOLD_STDEV_MULT * stdev(series),
# floored at OPEN_THRESHOLD_MIN_MARGIN above the median. [UNCALIBRATED] initial guess.
OPEN_THRESHOLD_STDEV_MULT = 0.5
OPEN_THRESHOLD_MIN_MARGIN = 0.02

Sample = Tuple[float, float]  # (time_seconds, lip_openness_ratio)


def to_container_time(word_timestamps: Optional[List[Dict[str, Any]]], audio_start_seconds: float) -> Optional[List[Dict[str, Any]]]:
    """
    Word times from the speech recognizer are relative to the extracted WAV, whose first sample
    is the first sample of the audio track. The lip series uses the container clock, where the
    audio track may start later (a probe on a clip with the audio delayed by 0.3 s showed the
    extracted audio losing that offset). Adding the audio start puts both on one clock. A start
    slightly below zero (the Opus pre-skip, about -0.007 s) is treated as zero.
    """
    if not word_timestamps:
        return word_timestamps
    offset = max(0.0, audio_start_seconds)
    return [{**w, "start": w["start"] + offset, "end": w["end"] + offset} for w in word_timestamps]


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


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _extract_samples(series: List[Dict[str, Any]]) -> List[Sample]:
    """Keep only entries with a finite, non-negative `time_seconds` and a finite ratio."""
    return [
        (float(entry["time_seconds"]), float(entry["lip_openness_ratio"]))
        for entry in series
        if _is_finite_number(entry.get("time_seconds"))
        and entry["time_seconds"] >= 0
        and _is_finite_number(entry.get("lip_openness_ratio"))
    ]


def _open_threshold(ratios: List[float]) -> float:
    median = statistics.median(ratios)
    stdev = statistics.stdev(ratios) if len(ratios) > 1 else 0.0
    return median + max(OPEN_THRESHOLD_MIN_MARGIN, OPEN_THRESHOLD_STDEV_MULT * stdev)


def _word_is_aligned(word: Dict[str, Any], samples: List[Sample], open_threshold: float) -> Optional[bool]:
    window_start = word["start"] - ALIGNMENT_TOLERANCE_SECONDS
    window_end = word["end"] + ALIGNMENT_TOLERANCE_SECONDS
    overlapping = [ratio for t, ratio in samples if window_start <= t <= window_end]
    if not overlapping:
        return None
    open_fraction = sum(1 for ratio in overlapping if ratio >= open_threshold) / len(overlapping)
    return open_fraction >= WORD_OPEN_FRACTION_THRESHOLD


def _build_scored_result(judged: List[bool], word_count: int, sample_count: int, open_threshold: float) -> DetectorResult:
    aligned = sum(1 for r in judged if r)
    score = round(aligned / len(judged), 4)
    reason = (
        f"AV alignment: {aligned}/{len(judged)} words showed corresponding lip movement "
        f"(of {word_count} total words; {word_count - len(judged)} had no overlapping frames)."
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
            "words_aligned": aligned,
            "lip_samples_used": sample_count,
            "open_threshold": round(open_threshold, 4),
            "degraded": False,
        },
    )


def run_av_alignment(
    wav_path: Path | str,
    word_timestamps: Optional[List[Dict[str, Any]]] = None,
    lip_openness_data: Optional[Dict[str, Any]] = None,
) -> DetectorResult:
    """
    Execute Stage 4 AV Temporal Alignment.

    `lip_openness_data` shape: {"fps": float, "series": [{"frame_index": int,
    "time_seconds": float, "lip_openness_ratio": float}, ...]}, per av-alignment-interface.md;
    only `time_seconds` and `lip_openness_ratio` are read. `word_timestamps` shape:
    [{"word": str, "start": float, "end": float, "probability": float}, ...].
    """
    word_count = len(word_timestamps) if word_timestamps else 0

    if not word_timestamps:
        return _degraded_result("No word timestamps available for AV alignment.", word_count)
    if not lip_openness_data or not lip_openness_data.get("series"):
        return _degraded_result("No lip openness data available for AV alignment.", word_count)

    try:
        samples = _extract_samples(lip_openness_data["series"])
        if not samples:
            return _degraded_result(
                "Lip openness series has no usable time_seconds samples; "
                "frame_index/fps is not a trustworthy clock for browser recordings.",
                word_count,
            )

        open_threshold = _open_threshold([ratio for _, ratio in samples])
        results = [_word_is_aligned(word, samples, open_threshold) for word in word_timestamps]
        judged = [result for result in results if result is not None]
        if not judged:
            return _degraded_result(
                "No spoken word overlapped any sampled video frame (timing mismatch).", word_count
            )
        return _build_scored_result(judged, word_count, len(samples), open_threshold)
    except Exception as exc:  # noqa: BLE001 - a detector must never raise
        logger.exception("Unexpected error in run_av_alignment")
        return DetectorResult(
            score=None,
            passed=True,
            reason=f"AV alignment failed unexpectedly: {type(exc).__name__}: {exc}",
            error=str(exc),
            details={"av_alignment_score": None, "word_count": word_count, "degraded": True},
        )
