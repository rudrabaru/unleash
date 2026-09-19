"""
Stage 2: Phrase Compliance (STT + Word Matching) Implementation.

Transcribes audio using faster-whisper (tiny model) on CPU, extracts word-level
timestamps and confidences, and verifies compliance against a 5-word phrase
challenge using weighted edit distance + minimum-average-confidence.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.detector import DetectorResult

logger = logging.getLogger(__name__)

# faster-whisper tiny loaded ONCE at module init (known-tricky-spots #1, #4)
_WHISPER_MODEL: Optional[Any] = None
_WHISPER_LOAD_ERROR: Optional[str] = None
_WHISPER_LOAD_TIME_S: float = 0.0

try:
    _t0 = time.perf_counter()
    from faster_whisper import WhisperModel

    # Load tiny model with int8 quantization for optimal CPU inference speed
    _WHISPER_MODEL = WhisperModel("tiny", device="cpu", compute_type="int8")
    _WHISPER_LOAD_TIME_S = time.perf_counter() - _t0
    logger.info(f"faster-whisper (tiny/int8) loaded successfully in {_WHISPER_LOAD_TIME_S:.3f}s")
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


def word_similarity_score(recognized: str, target: str) -> float:
    """
    Compute word-level similarity (0.0-1.0) using Levenshtein distance.
    Maximum distance for penalizing errors is 2x the longer word length (very lenient).
    """
    distance = levenshtein_distance(recognized.lower(), target.lower())
    max_distance = max(len(recognized), len(target)) * 2
    if max_distance == 0:
        return 1.0
    return max(0.0, 1.0 - (distance / max_distance))


def match_words_fuzzy(
    recognized_words: List[Tuple[str, float]],
    target_words: List[str],
    min_avg_confidence: float = 0.5,
    min_word_similarity: float = 0.6,
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
        best_sim = min_word_similarity

        for i, (rec_word, confidence) in enumerate(recognized_words):
            if i in used_indices:
                continue

            # Only consider words with sufficient confidence
            if confidence < min_avg_confidence:
                continue

            similarity = word_similarity_score(rec_word, target_word)
            if similarity > best_sim:
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


def run_phrase_compliance(
    wav_path: Path | str,
    challenge_phrase: str,
    threshold: int = 4,
    min_avg_confidence: float = 0.5,
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

    # 1. Check model initialization
    if _WHISPER_MODEL is None:
        err_msg = f"Whisper backend not initialized: {_WHISPER_LOAD_ERROR or 'Unknown init error'}"
        return DetectorResult(
            score=None,
            passed=False,
            reason="Phrase compliance check unavailable due to Whisper model initialization error.",
            error=err_msg,
            details={
                "phrase_matched": False,
                "words_detected": [],
                "target_words": [],
                "match_count": 0,
                "transcript": "",
                "word_timestamps": []
            }
        )

    # 2. Validate and parse challenge phrase (space-separated words)
    target_words = challenge_phrase.lower().strip().split()
    if len(target_words) != 5:
        return DetectorResult(
            score=None,
            passed=False,
            reason=f"Invalid challenge phrase '{challenge_phrase}': Expected exactly 5 words.",
            error="Invalid challenge phrase format",
            details={
                "phrase_matched": False,
                "words_detected": [],
                "target_words": target_words,
                "match_count": 0,
                "transcript": "",
                "word_timestamps": []
            }
        )

    # 3. Check audio file existence
    if not path_obj.exists():
        return DetectorResult(
            score=None,
            passed=False,
            reason=f"Audio file not found: {path_obj}",
            error="Audio file does not exist",
            details={
                "phrase_matched": False,
                "words_detected": [],
                "target_words": target_words,
                "match_count": 0,
                "transcript": "",
                "word_timestamps": []
            }
        )

    try:
        t_infer_start = time.perf_counter()

        # Run transcription with word-level timestamps and per-word confidence
        segments, info = _WHISPER_MODEL.transcribe(
            str(path_obj),
            beam_size=5,
            language="en",
            word_timestamps=True,
            vad_filter=False,  # Stage 1 already filtered via silero-vad
            temperature=0.0
        )

        segments_list = list(segments)
        infer_duration = round(time.perf_counter() - t_infer_start, 3)

        transcript = " ".join(s.text.strip() for s in segments_list).strip()

        # Extract word timestamps and confidence (critical for Stage 4 AV alignment)
        word_timestamps: List[Dict[str, Any]] = []
        recognized_words: List[Tuple[str, float]] = []

        for seg in segments_list:
            if seg.words:
                for w in seg.words:
                    clean_w = w.word.strip()
                    if clean_w:
                        word_timestamps.append({
                            "word": clean_w,
                            "start": round(w.start, 3),
                            "end": round(w.end, 3),
                            "probability": round(w.probability, 3)
                        })
                        recognized_words.append((clean_w, w.probability))

        # Perform fuzzy phrase matching
        match_count, matched_pairs, avg_confidence = match_words_fuzzy(
            recognized_words=recognized_words,
            target_words=target_words,
            min_avg_confidence=min_avg_confidence,
            min_word_similarity=0.6
        )

        passed = match_count >= threshold
        score = round(match_count / 5.0, 2)

        if passed:
            reason = (
                f"Phrase compliance verified: {match_count}/5 words matched "
                f"(challenge: {' '.join(target_words)}). "
                f"Matched pairs: {', '.join(matched_pairs)}. "
                f"Average confidence: {avg_confidence:.3f}. "
                f"Transcript: '{transcript}'."
            )
        else:
            if not recognized_words:
                reason = (
                    f"Phrase compliance failed: No words detected in transcript "
                    f"(expected {' '.join(target_words)}). Transcript: '{transcript}'."
                )
            else:
                reason = (
                    f"Phrase compliance failed: Only {match_count}/5 words matched "
                    f"(challenge: {' '.join(target_words)}). "
                    f"Matched pairs: {', '.join(matched_pairs) if matched_pairs else 'none'}. "
                    f"Transcript: '{transcript}'."
                )

        return DetectorResult(
            score=score,
            passed=passed,
            reason=reason,
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
                "whisper_model": "tiny",
                "compute_type": "int8"
            }
        )

    except Exception as e:
        logger.exception("Unexpected error in run_phrase_compliance")
        return DetectorResult(
            score=None,
            passed=False,
            reason=f"Stage 2 Phrase Compliance failed unexpectedly: {type(e).__name__}: {e}",
            error=f"{type(e).__name__}: {e}",
            details={
                "phrase_matched": False,
                "words_detected": [],
                "target_words": target_words,
                "match_count": 0,
                "transcript": "",
                "word_timestamps": []
            }
        )
