"""
Audio Pipeline Module (Owned by Dev 1)
- Stage 1: Speech Gate (silero-vad) [REAL]
- Stage 2: Phrase Compliance (faster-whisper tiny) [REAL]
- Stage 3: Voice Authenticity (librosa spectral heuristics) [REAL]
- Stage 4: AV Temporal Alignment (Whisper word timestamps x MediaPipe lip series) [STUB]
"""
from __future__ import annotations

import logging
from pathlib import Path
from app.modules.audio._av_alignment import run_av_alignment
from app.modules.audio._extraction import (
    check_extraction_completeness,
    extract_wav,
    probe_media,
    verify_wav,
)
from app.modules.audio._phrase_compliance import run_phrase_compliance
from app.modules.audio._speech_gate import run_speech_gate
from app.modules.audio._voice_authenticity import run_voice_authenticity
from app.schemas.detector import DetectorResult

from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# Audio advisory score weights (Stage 3: 10% + Stage 4: 10% in system fusion)
# Within the audio module, each contributes equally to the advisory score field.
_STAGE3_ADVISORY_WEIGHT: float = 0.5
_STAGE4_ADVISORY_WEIGHT: float = 0.5


def _merge_stage_details(*stage_results: Optional[DetectorResult]) -> Dict[str, Any]:
    """Merge details dictionary across multiple detector results in sequence."""
    merged: Dict[str, Any] = {}
    for res in stage_results:
        if res is not None and res.details:
            merged.update(res.details)
    return merged


def _compute_pipeline_score(
    stage3_result: DetectorResult,
    stage4_score: Optional[float] = None,
) -> Tuple[Optional[float], str]:
    """
    Derive composite pipeline advisory score and its formatted string representation.
    Stage 3 and Stage 4 (when implemented) contribute to the advisory score.
    """
    s3_score = stage3_result.score
    active_weight = 0.0
    weighted_sum = 0.0

    if s3_score is not None:
        weighted_sum += s3_score * _STAGE3_ADVISORY_WEIGHT
        active_weight += _STAGE3_ADVISORY_WEIGHT

    if stage4_score is not None:
        weighted_sum += stage4_score * _STAGE4_ADVISORY_WEIGHT
        active_weight += _STAGE4_ADVISORY_WEIGHT

    if active_weight > 0:
        combined_score = round(weighted_sum / active_weight, 3)
        s3_str = f"{s3_score:.3f}" if s3_score is not None else "N/A"
        return combined_score, s3_str

    return None, "N/A"


def _build_pipeline_reason(
    s1_details: Dict[str, Any],
    s2_details: Dict[str, Any],
    s3_str: str,
) -> str:
    """Build standardized human-readable reason string when all mandatory stages pass."""
    speech_dur = s1_details.get("speech_duration_seconds", 0.0)
    match_count = s2_details.get("match_count", 0)
    return (
        f"Stages 1+2 passed: {speech_dur:.2f}s speech detected, "
        f"{match_count}/3 challenge digits verified. "
        f"Stage 3 voice authenticity: {s3_str}. [STUB: Stage 4 passed]"
    )


def _cleanup_temp_file(file_path: Optional[Path]) -> None:
    """Safely delete temporary intermediate file if it exists (Privacy NFR §10)."""
    if file_path is not None:
        try:
            if file_path.exists():
                file_path.unlink()
        except OSError as e:
            logger.warning(f"Could not delete temporary WAV file {file_path}: {e}")


async def process_audio_pipeline(media_path: str, challenge_phrase: str) -> DetectorResult:
    """
    Execute the audio pipeline stages in sequence:
    1. Extract audio track from media container to 16kHz mono WAV in temp_uploads/
    2. Verify extraction completeness and audio format contract
    3. Stage 1 (Speech Gate - silero-vad): Hard gate on speech presence & duration >= 2.0s
    4. Stage 2 (Phrase Compliance - faster-whisper tiny): Hard gate on 2-of-3 challenge digits match
    5. Stage 3 (Voice Authenticity - librosa spectral heuristics): Advisory score (noise floor, flux, hf rolloff)
    6. Stage 4 (AV Alignment): Currently stub.
    
    Guarantees:
    - Never raises an uncaught exception (complies with 4-key contract).
    - Hard gate failure immediately stops pipeline execution and returns passed=False.
    - Temporary extracted WAV is deleted post-analysis (Privacy NFR §10).
    """
    wav_path: Optional[Path] = None
    try:
        src_path = Path(media_path)
        if not src_path.exists():
            return DetectorResult(
                score=None,
                passed=False,
                reason=f"Media file does not exist: {media_path}",
                error="Media file not found",
                details={"speech_detected": False, "speech_duration_seconds": 0.0},
            )

        # 1. Probe input container and audio streams
        container_info = probe_media(src_path)
        if not container_info["ok"]:
            return DetectorResult(
                score=None,
                passed=False,
                reason=f"Failed to probe media file: {container_info.get('error')}",
                error=container_info.get("error") or "Media probe failed",
                details={"speech_detected": False, "speech_duration_seconds": 0.0},
            )

        if container_info.get("audio") is None:
            return DetectorResult(
                score=None,
                passed=False,
                reason="No audio stream found in media container.",
                error="No audio stream",
                details={"speech_detected": False, "speech_duration_seconds": 0.0},
            )

        # 2. Setup output WAV path in backend/temp_uploads/ with session/media prefix
        backend_dir = Path(__file__).resolve().parent.parent.parent.parent
        temp_uploads_dir = backend_dir / "temp_uploads"
        temp_uploads_dir.mkdir(parents=True, exist_ok=True)

        stem = src_path.stem
        wav_path = temp_uploads_dir / f"{stem}_16k.wav"

        # 3. Extract to 16kHz mono WAV via ffmpeg subprocess
        ok, extract_err, _ = extract_wav(src_path, wav_path)
        if not ok:
            return DetectorResult(
                score=None,
                passed=False,
                reason=f"Failed to extract audio track: {extract_err}",
                error=extract_err or "Audio extraction failed",
                details={"speech_detected": False, "speech_duration_seconds": 0.0},
            )

        try:
            # 4. Verify output WAV satisfies resample contract (16000Hz mono PCM)
            vok, vdesc = verify_wav(wav_path)
            if not vok:
                return DetectorResult(
                    score=None,
                    passed=False,
                    reason=f"Extracted audio failed format verification: {vdesc}",
                    error=vdesc,
                    details={"speech_detected": False, "speech_duration_seconds": 0.0},
                )

            # 5. Check extraction completeness (compare against container duration)
            wav_info = probe_media(wav_path)
            extracted_dur = wav_info.get("duration")
            claimed_dur = container_info.get("duration")
            is_complete, comp_err = check_extraction_completeness(claimed_dur, extracted_dur)
            if not is_complete:
                return DetectorResult(
                    score=None,
                    passed=False,
                    reason=f"Extraction truncation detected: {comp_err}",
                    error=f"Extraction truncated ({comp_err})",
                    details={
                        "speech_detected": False,
                        "speech_duration_seconds": 0.0,
                        "extracted_duration": extracted_dur,
                        "claimed_duration": claimed_dur,
                    },
                )

            # 6. Run Stage 1 Speech Gate (silero-vad)
            stage1_result = run_speech_gate(wav_path)

            # If Stage 1 produced an internal error or failed the hard gate, return immediately
            if stage1_result.error is not None:
                return stage1_result

            if not stage1_result.passed:
                return DetectorResult(
                    score=None,
                    passed=False,
                    reason=stage1_result.reason,
                    error=None,
                    details=stage1_result.details,
                )

            # 7. Run Stage 2 Phrase Compliance (faster-whisper)
            stage2_result = run_phrase_compliance(wav_path, challenge_phrase)

            # If Stage 2 produced an internal error or failed the hard gate, return immediately
            if stage2_result.error is not None:
                return DetectorResult(
                    score=None,
                    passed=False,
                    reason=stage2_result.reason,
                    error=stage2_result.error,
                    details=_merge_stage_details(stage1_result, stage2_result),
                )

            if not stage2_result.passed:
                return DetectorResult(
                    score=None,
                    passed=False,
                    reason=stage2_result.reason,
                    error=None,
                    details=_merge_stage_details(stage1_result, stage2_result),
                )

            # 8. Run Stage 3 Voice Authenticity (librosa spectral heuristics - advisory)
            stage1_segments = stage1_result.details.get("segments") if stage1_result.details else None
            stage3_result = run_voice_authenticity(wav_path, stage1_segments)

            # 9. Run Stage 4 AV Temporal Alignment (Whisper word timestamps x lip data - advisory stub)
            word_timestamps = stage2_result.details.get("word_timestamps") if stage2_result.details else None
            stage4_result = run_av_alignment(wav_path, word_timestamps=word_timestamps, lip_openness_data=None)

            # 10. Stages 1 & 2 Passed -> Fold into pipeline result
            combined_details = _merge_stage_details(stage1_result, stage2_result, stage3_result, stage4_result)

            combined_score, s3_str = _compute_pipeline_score(stage3_result, stage4_score=stage4_result.score)
            pipeline_reason = _build_pipeline_reason(
                stage1_result.details or {},
                stage2_result.details or {},
                s3_str,
            )

            return DetectorResult(
                score=combined_score,
                passed=True,
                reason=pipeline_reason,
                error=None,
                details=combined_details,
            )
        finally:
            _cleanup_temp_file(wav_path)

    except Exception as e:
        logger.exception("Unexpected error in process_audio_pipeline")
        return DetectorResult(
            score=None,
            passed=False,
            reason=f"Audio pipeline failed with unexpected error: {type(e).__name__}: {e}",
            error=f"{type(e).__name__}: {e}",
            details={"speech_detected": False, "speech_duration_seconds": 0.0},
        )

