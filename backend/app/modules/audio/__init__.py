"""
Audio pipeline. Extracts the audio track, then runs four checks in order:
- speech check (silero-vad): must pass
- phrase check (faster-whisper base.en word matching, 4 of 5 words): must pass
- voice-authenticity check (librosa spectral heuristics): advisory
- lip-sync check (Whisper word times against the MediaPipe lip series): advisory

A failed must-pass check stops the pipeline and returns passed=False.
"""
from __future__ import annotations

import logging
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from app.core.config import settings
from app.modules.audio._av_alignment import run_av_alignment, to_container_time
from app.modules.audio._extraction import (
    check_extraction_completeness,
    extract_wav,
    probe_media,
    verify_wav,
)
from app.modules.audio._phrase_compliance import CHALLENGE_WORD_COUNT, run_phrase_compliance
from app.modules.audio._speech_gate import run_speech_gate
from app.modules.audio._voice_authenticity import run_voice_authenticity
from app.schemas.detector import DetectorResult

logger = logging.getLogger(__name__)

# The two advisory checks contribute equally to the composite advisory score.
_VOICE_CHECK_WEIGHT: float = 0.5
_LIP_SYNC_WEIGHT: float = 0.5


def _failure(reason: str, error: Optional[str] = None, **details: Any) -> DetectorResult:
    """A failed pipeline result: no score, passed=False, and the speech fields consumers expect."""
    return DetectorResult(
        score=None,
        passed=False,
        reason=reason,
        error=error,
        details={"speech_detected": False, "speech_duration_seconds": 0.0, **details},
    )


def _merge_details(*results: DetectorResult) -> Dict[str, Any]:
    """Merge the details of several check results, later results winning on a repeated key."""
    merged: Dict[str, Any] = {}
    for result in results:
        if result.details:
            merged.update(result.details)
    return merged


def _compute_pipeline_score(
    voice_result: DetectorResult,
    lip_sync_score: Optional[float] = None,
) -> Tuple[Optional[float], str]:
    """
    Composite advisory score and the voice-check score as text. Only checks that produced a
    score contribute; with none, the score is None.
    """
    parts = [(voice_result.score, _VOICE_CHECK_WEIGHT), (lip_sync_score, _LIP_SYNC_WEIGHT)]
    measured = [(score, weight) for score, weight in parts if score is not None]
    voice_text = f"{voice_result.score:.3f}" if voice_result.score is not None else "N/A"
    if not measured:
        return None, voice_text
    total_weight = sum(weight for _, weight in measured)
    return round(sum(score * weight for score, weight in measured) / total_weight, 3), voice_text


def _build_pipeline_reason(
    speech_details: Dict[str, Any],
    phrase_details: Dict[str, Any],
    voice_text: str,
    lip_sync_reason: str,
) -> str:
    """Human-readable reason for a run in which both must-pass checks passed."""
    speech_seconds = speech_details.get("speech_duration_seconds", 0.0)
    matched = phrase_details.get("match_count", 0)
    return (
        f"Speech and phrase checks passed: {speech_seconds:.2f}s speech detected, "
        f"{matched}/{CHALLENGE_WORD_COUNT} challenge words verified. "
        f"Voice authenticity: {voice_text}. Lip sync: {lip_sync_reason}"
    )


@dataclass
class _Prepared:
    """The extracted 16 kHz WAV and the container probe, or the failure that stopped extraction."""
    wav_path: Optional[Path] = None
    container_info: Optional[Dict[str, Any]] = None
    failure: Optional[DetectorResult] = None


def _prepare_wav(src_path: Path, workdir: Path) -> _Prepared:
    """Probe the media, extract its audio to a 16 kHz mono WAV in `workdir` and verify the result."""
    if not src_path.exists():
        return _Prepared(failure=_failure(f"Media file does not exist: {src_path}", "Media file not found"))

    info = probe_media(src_path)
    if not info["ok"]:
        return _Prepared(failure=_failure(
            f"Failed to probe media file: {info.get('error')}", info.get("error") or "Media probe failed"
        ))
    if info.get("audio") is None:
        return _Prepared(failure=_failure("No audio stream found in media container.", "No audio stream"))

    wav_path = workdir / f"{src_path.stem}_16k.wav"
    ok, error, _ = extract_wav(src_path, wav_path)
    if not ok:
        return _Prepared(failure=_failure(f"Failed to extract audio track: {error}", error or "Audio extraction failed"))

    ok, description = verify_wav(wav_path)
    if not ok:
        return _Prepared(failure=_failure(f"Extracted audio failed format verification: {description}", description))

    extracted = probe_media(wav_path).get("duration")
    complete, truncation_error = check_extraction_completeness(info.get("duration"), extracted)
    if not complete:
        return _Prepared(failure=_failure(
            f"Extraction truncation detected: {truncation_error}",
            f"Extraction truncated ({truncation_error})",
            extracted_duration=extracted,
            claimed_duration=info.get("duration"),
        ))
    return _Prepared(wav_path=wav_path, container_info=info)


def _timed(check: Callable[..., DetectorResult], *args: Any, **kwargs: Any) -> Tuple[DetectorResult, float]:
    started = time.perf_counter()
    result = check(*args, **kwargs)
    return result, round(time.perf_counter() - started, 3)


def _run_lip_sync(prepared: _Prepared, phrase: DetectorResult, lip_openness_data) -> DetectorResult:
    """Lip-sync check on word times converted to the container clock the lip series uses."""
    words = (phrase.details or {}).get("word_timestamps")
    audio_start = prepared.container_info["audio"].get("start_time") or 0.0
    result, seconds = _timed(
        run_av_alignment,
        word_timestamps=to_container_time(words, audio_start),
        lip_openness_data=lip_openness_data,
    )
    result.details = {
        **(result.details or {}),
        "lip_sync_latency_seconds": seconds,
        "audio_start_offset_seconds": round(max(0.0, audio_start), 3),
    }
    return result


def _run_checks(prepared: _Prepared, challenge_phrase: str, lip_openness_data) -> DetectorResult:
    speech = run_speech_gate(prepared.wav_path)
    if speech.error is not None:
        return speech
    if not speech.passed:
        return DetectorResult(score=None, passed=False, reason=speech.reason, error=None, details=speech.details)

    phrase, phrase_seconds = _timed(run_phrase_compliance, prepared.wav_path, challenge_phrase)
    phrase.details = {**(phrase.details or {}), "phrase_check_latency_seconds": phrase_seconds}
    if phrase.error is not None or not phrase.passed:
        return DetectorResult(
            score=None, passed=False, reason=phrase.reason, error=phrase.error,
            details=_merge_details(speech, phrase),
        )

    voice = run_voice_authenticity(prepared.wav_path, (speech.details or {}).get("segments"))
    lip_sync = _run_lip_sync(prepared, phrase, lip_openness_data)

    details = _merge_details(speech, phrase, voice, lip_sync)
    for name, check in (("voice_check_error", voice), ("lip_sync_error", lip_sync)):
        if check.error is not None:
            details[name] = check.error  # advisory errors do not fail the run but must stay visible

    score, voice_text = _compute_pipeline_score(voice, lip_sync_score=lip_sync.score)
    return DetectorResult(
        score=score,
        passed=True,
        reason=_build_pipeline_reason(speech.details or {}, phrase.details or {}, voice_text, lip_sync.reason),
        error=None,
        details=details,
    )


def process_audio_pipeline(
    media_path: str,
    challenge_phrase: str,
    lip_openness_data: Optional[Dict[str, Any]] = None,
) -> DetectorResult:
    """
    Run the audio checks on a recording and fold them into one DetectorResult.

    The extracted WAV lives in a temporary folder that is always deleted afterwards, whether the
    run passes, fails or raises. Never raises.
    """
    try:
        upload_dir = Path(settings.UPLOAD_TEMP_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=upload_dir, prefix="audio_") as workdir:
            prepared = _prepare_wav(Path(media_path), Path(workdir))
            if prepared.failure is not None:
                return prepared.failure
            return _run_checks(prepared, challenge_phrase, lip_openness_data)
    except Exception as e:  # noqa: BLE001 - a detector must never raise
        logger.exception("Unexpected error in process_audio_pipeline")
        return _failure(
            f"Audio pipeline failed with unexpected error: {type(e).__name__}: {e}",
            f"{type(e).__name__}: {e}",
        )
