"""
Stage 2: Phrase Compliance (STT + Word Matching) Implementation.

Transcribes audio using faster-whisper (base.en model, decision D-18) on CPU, extracts
word-level timestamps and confidences, and verifies compliance against a 5-word phrase
challenge using 1x-normalized edit distance + a per-word confidence floor.

No vocabulary `initial_prompt` is used: it lifted genuine recall but made Whisper emit
vocabulary words on noise and tones ("zucchini" x6 on noise), which is a false-accept
channel for a hard gate (bake-off: backend/prototypes/stage2_bakeoff.py, decision D-23).
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.detector import DetectorResult

logger = logging.getLogger(__name__)

# Chosen by the Stage 2 bake-off (D-18/D-23): English-only, so isolated uncommon nouns are
# decoded as English words instead of the multilingual tiny model's "Lenton"/"Nappal".
WHISPER_MODEL_NAME: str = "base.en"
WHISPER_COMPUTE_TYPE: str = "int8"

# Per-word Whisper probability a recognized word needs before it can satisfy a challenge word.
# Kept at 0.5 (D-18: base.en passes the real take without lowering it). Lowering it is a hard-gate
# threshold change (D-04) and waits for >= 10 genuine takes from >= 3 speakers.
MIN_WORD_CONFIDENCE: float = 0.5

# faster-whisper loaded ONCE at module init (known-tricky-spots #1, #4)
_WHISPER_MODEL: Optional[Any] = None
_WHISPER_LOAD_ERROR: Optional[str] = None
_WHISPER_LOAD_TIME_S: float = 0.0

try:
    _t0 = time.perf_counter()
    from faster_whisper import WhisperModel

    # int8 quantization for CPU inference speed
    _WHISPER_MODEL = WhisperModel(WHISPER_MODEL_NAME, device="cpu", compute_type=WHISPER_COMPUTE_TYPE)
    _WHISPER_LOAD_TIME_S = time.perf_counter() - _t0
    logger.info(
        f"faster-whisper ({WHISPER_MODEL_NAME}/{WHISPER_COMPUTE_TYPE}) loaded successfully "
        f"in {_WHISPER_LOAD_TIME_S:.3f}s"
    )
except Exception as _e:  # noqa: BLE001
    _WHISPER_LOAD_ERROR = f"{type(_e).__name__}: {_e}"
    _WHISPER_MODEL = None
    logger.error(f"Failed to load faster-whisper model at module init: {_WHISPER_LOAD_ERROR}")


def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Compute Levenshtein (edit) distance between two strings.
    Used for word-level fuzzy matching against the challenge phrase vocabulary.
    """
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])

    return dp[m][n]


# Minimum per-word similarity for a recognized word to count as a challenge word.
# 0.8 on a 1x-length-normalized edit distance tolerates one slip in a 5+ letter word
# (e.g. "bridget" -> "bridge" = 0.86) but rejects unrelated words. The previous 2x
# normalization floored any two words at 0.5 and let ~90% of filler speech through.
MIN_WORD_SIMILARITY: float = 0.8


def normalize_word(word: str) -> str:
    """Lowercase and strip everything but letters (Whisper emits tokens like 'Apple,')."""
    return re.sub(r"[^a-z]", "", word.lower())


def word_similarity_score(recognized: str, target: str) -> float:
    """
    Compute word-level similarity (0.0-1.0): 1 - edit_distance / longer_word_length.
    Both words are normalized first, so case and punctuation never affect the score.
    """
    a, b = normalize_word(recognized), normalize_word(target)
    longest = max(len(a), len(b))
    if longest == 0:
        return 1.0
    return max(0.0, 1.0 - levenshtein_distance(a, b) / longest)


def match_words_fuzzy(
    recognized_words: List[Tuple[str, float]],
    target_words: List[str],
    min_avg_confidence: float = 0.5,
    min_word_similarity: float = MIN_WORD_SIMILARITY,
) -> Tuple[int, List[str], float]:
    """
    Perform fuzzy word matching between recognized and target phrase.

    Args:
        recognized_words: list of (word, confidence) tuples from Whisper
        target_words: list of target words from challenge phrase
        min_avg_confidence: minimum average confidence across matched words
        min_word_similarity: minimum per-word fuzzy-match score (0.0-1.0)

    Returns:
        (match_count, matched_word_pairs, avg_confidence)
            match_count: number of matched words (0 to len(target_words))
            matched_word_pairs: list of "recognized -> target" strings for logging
            avg_confidence: average confidence of matched words
    """
    if not recognized_words or not target_words:
        return 0, [], 0.0

    n_target = len(target_words)
    matched = 0
    matched_pairs = []
    confidence_sum = 0.0

    # Greedy matching: try to match each target word to best-available recognized word
    used_indices = set()

    for target_word in target_words:
        best_idx = -1
        best_sim = -1.0

        for i, (rec_word, confidence) in enumerate(recognized_words):
            if i in used_indices:
                continue

            # Only consider words with sufficient confidence
            if confidence < min_avg_confidence:
                continue

            similarity = word_similarity_score(rec_word, target_word)
            if similarity >= min_word_similarity and similarity > best_sim:
                best_idx = i
                best_sim = similarity

        if best_idx >= 0:
            rec_word, confidence = recognized_words[best_idx]
            matched += 1
            used_indices.add(best_idx)
            matched_pairs.append(f"{rec_word} -> {target_word}")
            confidence_sum += confidence

    avg_confidence = confidence_sum / matched if matched > 0 else 0.0
    return matched, matched_pairs, avg_confidence


CHALLENGE_WORD_COUNT: int = 5


def _failure_result(reason: str, error: str, target_words: List[str]) -> DetectorResult:
    """4-key failure result (score=None, passed=False) with the empty-details shape later stages expect."""
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
    """Return a failure result if the model, phrase or file is unusable; None when Stage 2 can run."""
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
        vad_filter=False,  # Stage 1 already filtered via silero-vad
        temperature=0.0,
    )
    segments_list = list(segments)
    return segments_list, info, round(time.perf_counter() - t0, 3)


def _collect_words(segments: List[Any]) -> Tuple[List[Dict[str, Any]], List[Tuple[str, float]]]:
    """Word timestamps (critical for Stage 4 AV alignment) and (word, probability) pairs."""
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
    passed: bool, match_count: int, target_words: List[str], matched_pairs: List[str],
    avg_confidence: float, transcript: str, heard_any_word: bool,
) -> str:
    challenge = " ".join(target_words)
    if passed:
        return (
            f"Phrase compliance verified: {match_count}/{CHALLENGE_WORD_COUNT} words matched "
            f"(challenge: {challenge}). Matched pairs: {', '.join(matched_pairs)}. "
            f"Average confidence: {avg_confidence:.3f}. Transcript: '{transcript}'."
        )
    if not heard_any_word:
        return (
            f"Phrase compliance failed: No words detected in transcript "
            f"(expected {challenge}). Transcript: '{transcript}'."
        )
    return (
        f"Phrase compliance failed: Only {match_count}/{CHALLENGE_WORD_COUNT} words matched "
        f"(challenge: {challenge}). Matched pairs: {', '.join(matched_pairs) if matched_pairs else 'none'}. "
        f"Transcript: '{transcript}'."
    )


def run_phrase_compliance(
    wav_path: Path | str,
    challenge_phrase: str,
    threshold: int = 4,
    min_avg_confidence: float = MIN_WORD_CONFIDENCE,
) -> DetectorResult:
    """
    Execute Stage 2 Phrase Compliance on a 16kHz mono WAV file.

    Hard gate requirements:
      - At least 4 of 5 challenge words must match (with fuzzy edit distance).
      - Each matched word must have >= min_avg_confidence (0.0-1.0).
      - Extracts and retains word-level timestamps in details for Stage 4 AV alignment.

    Guarantees:
      - Never raises an uncaught exception (4-key contract).
      - Returns a fully compliant DetectorResult.
      - Always populates word-level timestamps in details on successful transcription.
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

        match_count, matched_pairs, avg_confidence = match_words_fuzzy(
            recognized_words=recognized_words,
            target_words=target_words,
            min_avg_confidence=min_avg_confidence,
            min_word_similarity=MIN_WORD_SIMILARITY,
        )
        passed = match_count >= threshold

        return DetectorResult(
            score=round(match_count / CHALLENGE_WORD_COUNT, 2),
            passed=passed,
            reason=_build_reason(
                passed, match_count, target_words, matched_pairs, avg_confidence,
                transcript, bool(recognized_words),
            ),
            error=None,
            details={
                "phrase_matched": passed,
                "words_detected": [w for w, _ in recognized_words],
                "target_words": target_words,
                "match_count": match_count,
                "matched_pairs": matched_pairs,
                "average_confidence": round(avg_confidence, 3),
                "transcript": transcript,
                "word_timestamps": word_timestamps,
                "inference_duration_seconds": infer_duration,
                "language": getattr(info, "language", "en"),
                "whisper_model": WHISPER_MODEL_NAME,
                "compute_type": WHISPER_COMPUTE_TYPE,
                "min_word_confidence": min_avg_confidence,
            },
        )
    except Exception as e:  # noqa: BLE001 - a detector must never raise
        logger.exception("Unexpected error in run_phrase_compliance")
        return _failure_result(
            f"Stage 2 Phrase Compliance failed unexpectedly: {type(e).__name__}: {e}",
            f"{type(e).__name__}: {e}",
            target_words,
        )
