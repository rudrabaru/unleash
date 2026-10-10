"""
Phrase check (speech recognition plus word matching), the second must-pass audio check.

Transcribes audio with faster-whisper (the base.en model) on CPU, extracts word-level
timestamps and confidences, and verifies them against the 5-word challenge with an ordered
word alignment (`_phrase_align.py`): a length-normalised edit distance plus a per-word
confidence floor, the words in the challenge's order, and a cap on extra words.

No vocabulary `initial_prompt` is used: it lifted genuine recall but made Whisper emit
vocabulary words on noise and tones ("zucchini" x6 on noise), which would let non-speech
pass a must-pass check. The model was chosen by comparing candidates on recorded takes
(tools/phrase_model_comparison.py).
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.modules.audio._phrase_align import (  # noqa: F401 - re-exported: tests and tools import them from here
    MAX_INSERTED_WORDS,
    MIN_WORD_CONFIDENCE,
    MIN_WORD_SIMILARITY,
    Alignment,
    align_words,
    levenshtein_distance,
    normalize_word,
    word_similarity_score,
)
from app.schemas.detector import DetectorResult

logger = logging.getLogger(__name__)

# English-only, so isolated uncommon nouns are decoded as English words instead of the
# multilingual tiny model's "Lenton"/"Nappal" for "lantern"/"maple".
WHISPER_MODEL_NAME: str = "base.en"
WHISPER_COMPUTE_TYPE: str = "int8"

# faster-whisper is loaded ONCE at import, never per request (loading takes seconds and would
# exceed the token's lifetime if it happened inside a request).
_WHISPER_MODEL: Optional[Any] = None
_WHISPER_LOAD_ERROR: Optional[str] = None

try:
    from faster_whisper import WhisperModel

    _started = time.perf_counter()
    # int8 quantization for CPU inference speed
    _WHISPER_MODEL = WhisperModel(WHISPER_MODEL_NAME, device="cpu", compute_type=WHISPER_COMPUTE_TYPE)
    logger.info(
        "faster-whisper (%s/%s) loaded in %.3fs",
        WHISPER_MODEL_NAME, WHISPER_COMPUTE_TYPE, time.perf_counter() - _started,
    )
except Exception as _exc:  # noqa: BLE001
    _WHISPER_LOAD_ERROR = f"{type(_exc).__name__}: {_exc}"
    logger.error("Failed to load faster-whisper at import: %s", _WHISPER_LOAD_ERROR)


CHALLENGE_WORD_COUNT: int = 5


def _failure_result(reason: str, error: str, target_words: List[str]) -> DetectorResult:
    """Failure result (score=None, passed=False) with the empty-details shape the later checks expect."""
    return DetectorResult(
        score=None,
        passed=False,
        reason=reason,
        error=error,
        details={
            "phrase_matched": False,
            "words_detected": [],
            "target_words": target_words,
            "match_count": 0,
            "transcript": "",
            "word_timestamps": [],
        },
    )


def _precheck_failure(path_obj: Path, challenge_phrase: str, target_words: List[str]) -> Optional[DetectorResult]:
    """Return a failure result if the model, phrase or file is unusable; None when the phrase check can run."""
    if _WHISPER_MODEL is None:
        return _failure_result(
            "Phrase compliance check unavailable due to Whisper model initialization error.",
            f"Whisper backend not initialized: {_WHISPER_LOAD_ERROR or 'Unknown init error'}",
            [],
        )
    if len(target_words) != CHALLENGE_WORD_COUNT:
        return _failure_result(
            f"Invalid challenge phrase '{challenge_phrase}': Expected exactly {CHALLENGE_WORD_COUNT} words.",
            "Invalid challenge phrase format",
            target_words,
        )
    if not path_obj.exists():
        return _failure_result(f"Audio file not found: {path_obj}", "Audio file does not exist", target_words)
    return None


def _transcribe(path_obj: Path) -> Tuple[List[Any], Any, float]:
    """Run Whisper with word-level timestamps and per-word confidence. Returns (segments, info, seconds)."""
    t0 = time.perf_counter()
    segments, info = _WHISPER_MODEL.transcribe(
        str(path_obj),
        beam_size=5,
        language="en",
        word_timestamps=True,
        vad_filter=False,  # the speech check already ran silero-vad
        temperature=0.0,
    )
    segments_list = list(segments)
    return segments_list, info, round(time.perf_counter() - t0, 3)


def _collect_words(segments: List[Any]) -> Tuple[List[Dict[str, Any]], List[Tuple[str, float]]]:
    """Word timestamps (needed by the lip-sync check) and (word, probability) pairs."""
    word_timestamps: List[Dict[str, Any]] = []
    recognized_words: List[Tuple[str, float]] = []
    for seg in segments:
        for w in seg.words or []:
            clean_w = w.word.strip()
            if clean_w:
                word_timestamps.append({
                    "word": clean_w,
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "probability": round(w.probability, 3),
                })
                recognized_words.append((clean_w, w.probability))
    return word_timestamps, recognized_words


def _build_reason(
    passed: bool, alignment: Alignment, target_words: List[str], threshold: int, max_insertions: int,
    heard_any_word: bool,
) -> str:
    """The outcome in words. It never quotes what was heard: the reason is stored with the session."""
    challenge = " ".join(target_words)
    if passed:
        return (
            f"Phrase compliance verified: {alignment.match_count}/{CHALLENGE_WORD_COUNT} words matched in order "
            f"(challenge: {challenge}). Extra words: {alignment.insertions}. "
            f"Average confidence: {alignment.average_confidence:.3f}."
        )
    if not heard_any_word:
        return (
            f"Phrase compliance failed: No words detected in transcript "
            f"(expected {challenge})."
        )
    if alignment.match_count >= threshold:
        return (
            f"Phrase compliance failed: {alignment.match_count}/{CHALLENGE_WORD_COUNT} words matched in order but "
            f"{alignment.insertions} extra words were spoken (at most {max_insertions} allowed). "
            f"Challenge: {challenge}."
        )
    return (
        f"Phrase compliance failed: Only {alignment.match_count}/{CHALLENGE_WORD_COUNT} words matched in order "
        f"(challenge: {challenge})."
    )


def _success_details(
    passed, recognized_words, target_words, alignment, max_insertions,
    transcript, word_timestamps, infer_duration, info, min_word_confidence,
) -> Dict[str, Any]:
    return {
        "phrase_matched": passed,
        "words_detected": [w for w, _ in recognized_words],
        "target_words": target_words,
        "match_count": alignment.match_count,
        "matched_pairs": alignment.pairs,
        "insertions": alignment.insertions,
        "max_insertions": max_insertions,
        "average_confidence": round(alignment.average_confidence, 3),
        "transcript": transcript,
        "word_timestamps": word_timestamps,
        "inference_duration_seconds": infer_duration,
        "language": getattr(info, "language", "en"),
        "whisper_model": WHISPER_MODEL_NAME,
        "compute_type": WHISPER_COMPUTE_TYPE,
        "min_word_confidence": min_word_confidence,
    }


def run_phrase_compliance(
    wav_path: Path | str,
    challenge_phrase: str,
    threshold: int = 4,
    min_word_confidence: float = MIN_WORD_CONFIDENCE,
    max_insertions: int = MAX_INSERTED_WORDS,
) -> DetectorResult:
    """
    Run the phrase check on a 16kHz mono WAV file.

    Must-pass requirements:
      - At least 4 of 5 challenge words must be heard, IN ORDER (fuzzy edit distance).
      - Each matched word must have a recognition confidence >= min_word_confidence (0.0-1.0).
      - At most `max_insertions` heard words may match no challenge word.
      - Word-level timestamps are kept in details for the lip-sync check.

    Never raises; always returns a DetectorResult, with word timestamps on a successful transcription.
    """
    path_obj = Path(wav_path)
    target_words = challenge_phrase.lower().strip().split()

    failure = _precheck_failure(path_obj, challenge_phrase, target_words)
    if failure is not None:
        return failure

    try:
        segments, info, infer_duration = _transcribe(path_obj)
        transcript = " ".join(s.text.strip() for s in segments).strip()
        word_timestamps, recognized_words = _collect_words(segments)

        alignment = align_words(
            recognized_words, target_words,
            min_word_confidence=min_word_confidence, min_word_similarity=MIN_WORD_SIMILARITY,
        )
        passed = alignment.match_count >= threshold and alignment.insertions <= max_insertions

        return DetectorResult(
            score=round(alignment.match_count / CHALLENGE_WORD_COUNT, 2),
            passed=passed,
            reason=_build_reason(
                passed, alignment, target_words, threshold, max_insertions, bool(recognized_words),
            ),
            error=None,
            details=_success_details(
                passed, recognized_words, target_words, alignment, max_insertions,
                transcript, word_timestamps, infer_duration, info, min_word_confidence,
            ),
        )
    except Exception as e:  # noqa: BLE001 - a detector must never raise
        logger.exception("Unexpected error in run_phrase_compliance")
        return _failure_result(
            f"Phrase check failed unexpectedly: {type(e).__name__}: {e}",
            f"{type(e).__name__}: {e}",
            target_words,
        )
