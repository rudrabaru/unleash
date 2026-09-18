"""
Stage 2: Phrase Compliance (STT + Matching) Implementation.

Transcribes audio using faster-whisper (tiny model) on CPU, extracts word-level
timestamps, extracts spoken digits, and verifies compliance against the 3-digit
server challenge with a 2-of-3 match threshold.
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.schemas.detector import DetectorResult

logger = logging.getLogger(__name__)

# Digit word dictionaries
# Removed homophones that appear in normal speech (to/too/for/fore/o) to reduce false matches.
# Only kept exact digit names and phonetically-distinct alternatives (oh, won, ate).
SINGLE_DIGITS: Dict[str, int] = {
    "zero": 0, "oh": 0,
    "one": 1, "won": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8, "ate": 8,
    "nine": 9,
}

TEENS: Dict[str, int] = {
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}

TENS: Dict[str, int] = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40, "fourty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

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


def normalize_token(token: str) -> str:
    """Strip surrounding punctuation from a token."""
    return re.sub(r"^[^\w]+|[^\w]+$", "", token).lower()


def extract_digits(transcript: str) -> List[int]:
    """
    Extract a sequential list of individual integer digits (0-9) from a transcript string.
    Handles numeric characters, single-word digits, compound numbers ('forty-two', 'seven hundred'),
    and colloquial expressions.
    """
    if not transcript or not transcript.strip():
        return []

    # Replace hyphens/dashes with spaces for compound words (e.g. "forty-two" -> "forty two")
    text = transcript.replace("-", " ").replace("–", " ").replace("—", " ")

    # Pre-clean punctuation attached to numbers/words
    raw_tokens = text.split()
    tokens = [normalize_token(t) for t in raw_tokens if normalize_token(t)]

    extracted_digits: List[int] = []
    i = 0
    n = len(tokens)

    while i < n:
        token = tokens[i]

        # 1. Direct integer string (e.g. "742" or "7")
        if token.isdigit():
            for char in token:
                extracted_digits.append(int(char))
            i += 1
            continue

        # 2. Check for "hundred" construct: e.g. "seven hundred (and) forty two" or "seven hundred"
        if token in SINGLE_DIGITS and i + 1 < n and tokens[i + 1] == "hundred":
            extracted_digits.append(SINGLE_DIGITS[token])

            # Check if followed by "and" + tens/units or just tens/units
            offset = 2
            if i + offset < n and tokens[i + offset] == "and":
                offset += 1

            if i + offset < n and tokens[i + offset] in TENS:
                tens_val = TENS[tokens[i + offset]]
                tens_digit = tens_val // 10
                extracted_digits.append(tens_digit)
                offset += 1
                if i + offset < n and tokens[i + offset] in SINGLE_DIGITS:
                    extracted_digits.append(SINGLE_DIGITS[tokens[i + offset]])
                    offset += 1
                else:
                    extracted_digits.append(0)
            elif i + offset < n and tokens[i + offset] in TEENS:
                teen_val = TEENS[tokens[i + offset]]
                extracted_digits.extend([int(d) for d in str(teen_val)])
                offset += 1
            elif i + offset < n and tokens[i + offset] in SINGLE_DIGITS:
                extracted_digits.extend([0, SINGLE_DIGITS[tokens[i + offset]]])
                offset += 1
            else:
                # E.g. "seven hundred" -> [7, 0, 0]
                extracted_digits.extend([0, 0])

            i += offset
            continue

        # 3. Check for tens + units: e.g. "forty two" -> 42 -> [4, 2]
        if token in TENS:
            tens_digit = TENS[token] // 10
            extracted_digits.append(tens_digit)
            if i + 1 < n and tokens[i + 1] in SINGLE_DIGITS:
                extracted_digits.append(SINGLE_DIGITS[tokens[i + 1]])
                i += 2
            else:
                # E.g. "forty" -> [4, 0]
                extracted_digits.append(0)
                i += 1
            continue

        # 4. Check for teens: e.g. "fourteen" -> [1, 4]
        if token in TEENS:
            val = TEENS[token]
            extracted_digits.extend([int(d) for d in str(val)])
            i += 1
            continue

        # 5. Check for single digit word: e.g. "seven" -> 7
        if token in SINGLE_DIGITS:
            extracted_digits.append(SINGLE_DIGITS[token])
            i += 1
            continue

        # 6. Embedded digits in token (e.g. "7th" -> 7, or "x742y" -> [7, 4, 2])
        digits_in_token = re.findall(r"\d", token)
        if digits_in_token:
            extracted_digits.extend(int(d) for d in digits_in_token)

        i += 1

    return extracted_digits


def longest_common_subsequence(seq1: List[int], seq2: List[int]) -> int:
    """Dynamic programming longest common subsequence length."""
    m, n = len(seq1), len(seq2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq1[i - 1] == seq2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    return dp[m][n]


def positional_window_match(extracted: List[int], target: List[int]) -> int:
    """
    Find best match count via sliding window positional comparison or LCS.
    Handles extra leading/trailing numbers, background noise, and filler utterances.
    """
    if not extracted or not target:
        return 0

    t_len = len(target)
    e_len = len(extracted)

    # 1. Direct positional matching if same length
    if e_len == t_len:
        pos_match = sum(1 for a, b in zip(extracted, target) if a == b)
    else:
        # Sliding window positional match
        pos_match = 0
        if e_len >= t_len:
            for start in range(e_len - t_len + 1):
                window = extracted[start:start + t_len]
                match = sum(1 for a, b in zip(window, target) if a == b)
                if match > pos_match:
                    pos_match = match
        else:
            pos_match = sum(1 for a, b in zip(extracted, target[:e_len]) if a == b)

    # 2. LCS match (handles inserted noise / filler tokens)
    lcs_match = longest_common_subsequence(extracted, target)

    return max(pos_match, lcs_match)


def run_phrase_compliance(
    wav_path: Path | str,
    challenge_phrase: str,
    threshold: int = 2
) -> DetectorResult:
    """
    Execute Stage 2 Phrase Compliance on a 16kHz mono WAV file.
    
    Hard gate requirements:
      - At least 2 of 3 challenge digits must match the recognized transcript.
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
                "digits_detected": [],
                "target_digits": [],
                "match_count": 0,
                "transcript": "",
                "word_timestamps": []
            }
        )

    # 2. Validate challenge phrase
    target_digits = [int(d) for d in challenge_phrase if d.isdigit()]
    if len(target_digits) != 3:
        return DetectorResult(
            score=None,
            passed=False,
            reason=f"Invalid challenge phrase '{challenge_phrase}': Expected exactly 3 digits.",
            error="Invalid challenge phrase format",
            details={
                "phrase_matched": False,
                "digits_detected": [],
                "target_digits": target_digits,
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
                "digits_detected": [],
                "target_digits": target_digits,
                "match_count": 0,
                "transcript": "",
                "word_timestamps": []
            }
        )

    try:
        t_infer_start = time.perf_counter()

        # Run transcription with word-level timestamps
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

        # Extract word timestamps (critical for Stage 4 AV alignment)
        word_timestamps: List[Dict[str, Any]] = []
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

        # Extract digits & compute matching
        extracted_digits = extract_digits(transcript)
        match_count = positional_window_match(extracted_digits, target_digits)
        passed = match_count >= threshold
        score = round(match_count / 3.0, 2)

        if passed:
            reason = (
                f"Phrase compliance verified: {match_count}/3 digits matched "
                f"(expected {target_digits}, detected {extracted_digits}). "
                f"Transcript: '{transcript}'."
            )
        else:
            if not extracted_digits:
                reason = (
                    f"Phrase compliance failed: No digit words detected in transcript "
                    f"(expected {target_digits}). Transcript: '{transcript}'."
                )
            else:
                reason = (
                    f"Phrase compliance failed: Only {match_count}/3 digits matched "
                    f"(expected {target_digits}, detected {extracted_digits}). "
                    f"Transcript: '{transcript}'."
                )

        return DetectorResult(
            score=score,
            passed=passed,
            reason=reason,
            error=None,
            details={
                "phrase_matched": passed,
                "digits_detected": extracted_digits,
                "target_digits": target_digits,
                "match_count": match_count,
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
                "digits_detected": [],
                "target_digits": target_digits,
                "match_count": 0,
                "transcript": "",
                "word_timestamps": []
            }
        )
