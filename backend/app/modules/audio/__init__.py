"""
Audio Pipeline Module (Owned by Dev 1)
- Stage 1: Speech Gate (silero-vad) [REAL]
- Stage 2: Phrase Compliance (faster-whisper tiny) [STUB]
- Stage 3: Voice Authenticity (librosa spectral heuristics) [STUB]
- Stage 4: AV Temporal Alignment (Whisper word timestamps x MediaPipe lip series) [STUB]
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.modules.audio._extraction import (
    check_extraction_completeness,
    extract_wav,
    probe_media,
    verify_wav,
)
from app.modules.audio._speech_gate import run_speech_gate
from app.schemas.detector import DetectorResult

logger = logging.getLogger(__name__)


async def process_audio_pipeline(media_path: str, challenge_phrase: str) -> DetectorResult:
    """
    Execute the audio pipeline stages in sequence:
    1. Extract audio track from media container to 16kHz mono WAV in temp_uploads/
    2. Verify extraction completeness and audio format contract
    3. Stage 1 (Speech Gate - silero-vad): Hard gate on speech presence & duration >= 2.0s
    4. Stages 2-4 (Phrase Compliance, Voice Authenticity, AV Alignment): Currently stubs.
    
    Guarantees:
    - Never raises an uncaught exception (complies with 4-key contract).
    - Hard gate failure immediately stops pipeline execution and returns passed=False.
    """
    try:
        src_path = Path(media_path)
        if not src_path.exists():
            return DetectorResult(
                score=None,
                passed=False,
                reason=f"Media file does not exist: {media_path}",
                error="Media file not found",
                details={"speech_detected": False, "speech_duration_seconds": 0.0}
            )

        # 1. Probe input container and audio streams
        container_info = probe_media(src_path)
        if not container_info["ok"]:
            return DetectorResult(
                score=None,
                passed=False,
                reason=f"Failed to probe media file: {container_info.get('error')}",
                error=container_info.get("error") or "Media probe failed",
                details={"speech_detected": False, "speech_duration_seconds": 0.0}
            )

        if container_info.get("audio") is None:
            return DetectorResult(
                score=None,
                passed=False,
                reason="No audio stream found in media container.",
                error="No audio stream",
                details={"speech_detected": False, "speech_duration_seconds": 0.0}
            )

        # 2. Setup output WAV path in backend/temp_uploads/ with session/media prefix
        # Resolve backend base path
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
                details={"speech_detected": False, "speech_duration_seconds": 0.0}
            )

        # 4. Verify output WAV satisfies resample contract (16000Hz mono PCM)
        vok, vdesc = verify_wav(wav_path)
        if not vok:
            return DetectorResult(
                score=None,
                passed=False,
                reason=f"Extracted audio failed format verification: {vdesc}",
                error=vdesc,
                details={"speech_detected": False, "speech_duration_seconds": 0.0}
            )

        # 5. Check extraction completeness (Finding #2: compare against container duration)
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
                    "claimed_duration": claimed_dur
                }
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
                details=stage1_result.details
            )

        # 7. Stage 1 Passed -> Fold into pipeline result (Stages 2-4 are currently stubs)
        digits = [int(d) for d in challenge_phrase if d.isdigit()]
        combined_details = dict(stage1_result.details or {})
        combined_details.update({
            "phrase_matched": True,
            "digits_detected": digits,
            "voice_authenticity_score": 0.88,
            "av_alignment_score": 0.85,
            "extracted_wav_path": str(wav_path)
        })

        return DetectorResult(
            score=0.92,  # Stub score until Stages 2-4 are implemented
            passed=True,
            reason=f"Stage 1 Speech Gate passed ({stage1_result.details.get('speech_duration_seconds', 0.0):.2f}s speech). [STUB: Stages 2-4 passed]",
            error=None,
            details=combined_details
        )

    except Exception as e:
        logger.exception("Unexpected error in process_audio_pipeline")
        return DetectorResult(
            score=None,
            passed=False,
            reason=f"Audio pipeline failed with unexpected error: {type(e).__name__}: {e}",
            error=f"{type(e).__name__}: {e}",
            details={"speech_detected": False, "speech_duration_seconds": 0.0}
        )
