"""
Phrase check (speech recognition plus word matching), the second must-pass audio check.

Transcribes audio with faster-whisper (the base.en model) on CPU, extracts word-level
timestamps and confidences, and verifies them against the 5-word challenge using a
length-normalised edit distance plus a per-word confidence floor.

No vocabulary `initial_prompt` is used: it lifted genuine recall but made Whisper emit
vocabulary words on noise and tones ("zucchini" x6 on noise), which would let non-speech
pass a must-pass check. The model was chosen by comparing candidates on recorded takes
(tools/phrase_model_comparison.py).
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.detector import DetectorResult

logger = logging.getLogger(__name__)

# English-only, so isolated uncommon nouns are decoded as English words instead of the
# multilingual tiny model's "Lenton"/"Nappal" for "lantern"/"maple".
WHISPER_MODEL_NAME: str = "base.en"
WHISPER_COMPUTE_TYPE: str = "int8"

# Per-word Whisper probability a recognized word needs before it can satisfy a challenge word.
# Kept at 0.5: base.en passes the one real genuine take without lowering it. Lowering it changes
# a must-pass threshold and waits for >= 10 genuine takes from >= 3 speakers.
MIN_WORD_CONFIDENCE: float = 0.5

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
    min_word_confidence: float = MIN_WORD_CONFIDENCE,
    min_word_similarity: float = MIN_WORD_SIMILARITY,
) -> Tuple[int, List[str], float]:
    """
    Perform fuzzy word matching between recognized and target phrase.

    Args:
        recognized_words: list of (word, confidence) tuples from Whisper
        target_words: list of target words from challenge phrase
        min_word_confidence: a recognized word below this confidence is not considered
        min_word_similarity: minimum per-word fuzzy-match score (0.0-1.0)

    Returns:
        (match_count, matched_word_pairs, avg_confidence)
            match_count: number of matched words (0 to len(target_words))
            matched_word_pairs: list of "recognized -> target" strings for logging
            avg_confidence: average confidence of matched words
    """
    if not recognized_words or not target_words:
        return 0, [], 0.0

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
            if confidence < min_word_confidence:
                continue

            similarity = word_similarity_score(rec_word, target_word)
            if similarity >= min_word_similarity and similarity > best_sim:
                best_idx = i
                best_sim = similarity

        if best_idx != -1:
            rec_word, confidence = recognized_words[best_idx]
            matched += 1
            used_indices.add(best_idx)
            matched_pairs.append(f"{rec_word} -> {target_word}")
            confidence_sum += confidence

    avg_confidence = confidence_sum / matched if matched > 0 else 0.0
    return matched, matched_pairs, avg_confidence


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


def _success_details(
    passed, recognized_words, target_words, match_count, matched_pairs, avg_confidence,
    transcript, word_timestamps, infer_duration, info, min_word_confidence,
) -> Dict[str, Any]:
    return {
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
        "min_word_confidence": min_word_confidence,
    }


def run_phrase_compliance(
    wav_path: Path | str,
    challenge_phrase: str,
    threshold: int = 4,
    min_word_confidence: float = MIN_WORD_CONFIDENCE,
) -> DetectorResult:
    """
    Run the phrase check on a 16kHz mono WAV file.

    Must-pass requirements:
      - At least 4 of 5 challenge words must match (with fuzzy edit distance).
      - Each matched word must have a recognition confidence >= min_word_confidence (0.0-1.0).
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

        match_count, matched_pairs, avg_confidence = match_words_fuzzy(
            recognized_words=recognized_words,
            target_words=target_words,
            min_word_confidence=min_word_confidence,
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
            details=_success_details(
                passed, recognized_words, target_words, match_count, matched_pairs, avg_confidence,
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
