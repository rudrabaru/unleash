"""
Audio pipeline. Extracts the audio track, then runs four checks in order:
- speech check (silero-vad): must pass
- phrase check (faster-whisper base.en, at least 4 of 5 words in order, few extra words): must pass
- voice-authenticity check (librosa spectral heuristics): advisory
- lip-sync check (Whisper word times against the MediaPipe lip series): advisory

A failed must-pass check stops the pipeline and returns passed=False. Given the protocol windows
(`phases`), the speech and phrase checks and the lip-sync check look only at the Speak window; the
voice-authenticity check keeps the whole recording (the quiet parts around the speech are its
best evidence of a real room).
"""
from __future__ import annotations

import logging
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from app.core.config import settings
from app.modules.audio._io import read_wav_numpy
from app.modules.audio._av_alignment import run_av_alignment, to_container_time
from app.modules.audio._extraction import (
    check_extraction_completeness,
    extract_wav,
    probe_media,
    verify_wav,
)
from app.modules.audio._phrase_compliance import CHALLENGE_WORD_COUNT, run_phrase_compliance
from app.modules.audio._speak_crop import SpeakCrop, plan_speak_crop, write_speak_crop
from app.modules.audio._speech_gate import run_speech_gate
from app.modules.audio._voice_authenticity import run_voice_authenticity
from app.protocol import PhaseWindows
from app.schemas.detector import DetectorResult

logger = logging.getLogger(__name__)

# Below this RMS (full scale = 1.0, about -80 dBFS) the audio is digital silence: a muted or dead microphone.
SILENT_RMS: float = 1e-4

# Lip samples this far outside the Speak window still take part in the lip-sync check.
LIP_SERIES_MARGIN_SECONDS: float = 0.5


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


def _build_pipeline_reason(
    speech_details: Dict[str, Any],
    phrase_details: Dict[str, Any],
    voice: DetectorResult,
    lip_sync_reason: str,
) -> str:
    """Human-readable reason for a run in which both must-pass checks passed."""
    voice_text = f"{voice.score:.3f}" if voice.score is not None else "N/A"
    speech_seconds = speech_details.get("speech_duration_seconds", 0.0)
    matched = phrase_details.get("match_count", 0)
    return (
        f"Speech and phrase checks passed: {speech_seconds:.2f}s speech detected, "
        f"{matched}/{CHALLENGE_WORD_COUNT} challenge words verified. "
        f"Voice authenticity: {voice_text}. Lip sync: {lip_sync_reason}"
    )


@dataclass
class _Prepared:
    """The extracted 16 kHz WAV (and, with windows, its Speak crop) and the container probe, or the failure that stopped extraction."""
    wav_path: Optional[Path] = None
    container_info: Optional[Dict[str, Any]] = None
    failure: Optional[DetectorResult] = None
    crop: Optional[SpeakCrop] = None
    speak_wav: Optional[Path] = None

    @property
    def checked_wav(self) -> Path:
        """The audio the speech and phrase checks listen to: the Speak crop when there is one, else everything."""
        return self.speak_wav or self.wav_path

    @property
    def checked_offset(self) -> float:
        """Seconds into the extracted WAV at which `checked_wav` begins."""
        return self.crop.wav_start if self.crop else 0.0


def _with_speak_crop(prepared: _Prepared, phases: PhaseWindows, recording_start: Optional[float], workdir: Path) -> _Prepared:
    """`prepared` plus the Speak window cut out of its WAV (see _speak_crop.py)."""
    audio_start = max(0.0, prepared.container_info["audio"].get("start_time") or 0.0)
    crop = plan_speak_crop(phases, recording_start, audio_start)
    speak_wav = write_speak_crop(prepared.wav_path, crop, workdir / "speak_16k.wav")
    return _Prepared(wav_path=prepared.wav_path, container_info=prepared.container_info, crop=crop, speak_wav=speak_wav)


def _prepare_wav(
    src_path: Path,
    workdir: Path,
    phases: Optional[PhaseWindows] = None,
    recording_start: Optional[float] = None,
) -> _Prepared:
    """
    Probe the media, extract its audio to a 16 kHz mono WAV in `workdir` and verify the result. With
    `phases`, also cut the Speak window out of it.
    """
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
    prepared = _Prepared(wav_path=wav_path, container_info=info)
    return prepared if phases is None else _with_speak_crop(prepared, phases, recording_start, workdir)


def _trim_lip_series(lip_openness_data: Optional[Dict[str, Any]], crop: Optional[SpeakCrop]) -> Optional[Dict[str, Any]]:
    """The lip samples near the Speak window (half a second either side); the whole series without a crop."""
    if crop is None or not lip_openness_data or not lip_openness_data.get("series"):
        return lip_openness_data
    start, end = crop.container_start - LIP_SERIES_MARGIN_SECONDS, crop.container_end + LIP_SERIES_MARGIN_SECONDS
    kept = [s for s in lip_openness_data["series"] if s.get("time_seconds") is not None and start <= s["time_seconds"] <= end]
    return {**lip_openness_data, "series": kept}


def _shift_segments(segments: Optional[List[Dict[str, float]]], offset: float) -> Optional[List[Dict[str, float]]]:
    """Speech segments found in the crop, moved onto the whole WAV's timeline (for the voice check)."""
    if not segments or not offset:
        return segments
    return [{**s, "start": s["start"] + offset, "end": s["end"] + offset} for s in segments]


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
        # word times are relative to the checked audio, which may start partway into the WAV
        word_timestamps=to_container_time(words, audio_start + prepared.checked_offset),
        lip_openness_data=_trim_lip_series(lip_openness_data, prepared.crop),
    )
    result.details = {
        **(result.details or {}),
        "lip_sync_latency_seconds": seconds,
        "audio_start_offset_seconds": round(max(0.0, audio_start), 3),
    }
    return result


def _silent_capture(wav_path: Path) -> Optional[DetectorResult]:
    """
    A failed result when the checked audio is digital silence (a muted or dead microphone), else None.
    It is a capture problem, not a person who stayed quiet: a live microphone always records a little
    room noise, and the orchestrator turns this code into a request to try again.
    """
    audio, _, _ = read_wav_numpy(wav_path)
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2))) if len(audio) else 0.0
    if rms >= SILENT_RMS:
        return None
    return DetectorResult(
        score=None,
        passed=False,
        reason="No speech detected: the microphone recorded only silence.",
        error=None,
        details={"speech_detected": False, "speech_duration_seconds": 0.0, "failure_code": "mic_silent", "rms": rms},
    )


def _speak_window_details(prepared: _Prepared) -> Dict[str, Any]:
    """Which part of the recording the speech and phrase checks listened to."""
    if prepared.crop is None:
        return {"speak_window": None}
    crop = prepared.crop
    return {"speak_window": {
        "container_start": round(crop.container_start, 3),
        "container_end": round(crop.container_end, 3),
        "audio_seconds": round(crop.seconds, 3),
    }}


def _run_checks(prepared: _Prepared, challenge_phrase: str, lip_openness_data) -> DetectorResult:
    silent = _silent_capture(prepared.checked_wav)
    if silent is not None:
        return silent

    speech = run_speech_gate(prepared.checked_wav)
    if speech.error is not None:
        return speech
    if not speech.passed:
        return speech

    phrase, phrase_seconds = _timed(run_phrase_compliance, prepared.checked_wav, challenge_phrase)
    phrase.details = {
        **(phrase.details or {}),
        "phrase_check_latency_seconds": phrase_seconds,
        **_speak_window_details(prepared),
    }
    if phrase.error is not None or not phrase.passed:
        return DetectorResult(
            score=None, passed=False, reason=phrase.reason, error=phrase.error,
            details=_merge_details(speech, phrase),
        )

    voice = run_voice_authenticity(
        prepared.wav_path, _shift_segments((speech.details or {}).get("segments"), prepared.checked_offset)
    )
    lip_sync = _run_lip_sync(prepared, phrase, lip_openness_data)

    details = _merge_details(speech, phrase, voice, lip_sync)
    for name, check in (("voice_check_error", voice), ("lip_sync_error", lip_sync)):
        if check.error is not None:
            details[name] = check.error  # advisory errors do not fail the run but must stay visible

    return DetectorResult(
        score=None,  # the must-pass checks have no score; voice and lip sync are reported in the details
        passed=True,
        reason=_build_pipeline_reason(speech.details or {}, phrase.details or {}, voice, lip_sync.reason),
        error=None,
        details=details,
    )


def process_audio_pipeline(
    media_path: str,
    challenge_phrase: str,
    lip_openness_data: Optional[Dict[str, Any]] = None,
    phases: Optional[PhaseWindows] = None,
    recording_start: Optional[float] = None,
) -> DetectorResult:
    """
    Run the audio checks on a recording and fold them into one DetectorResult.

    With `phases` (the protocol windows) the speech, phrase and lip-sync checks use the Speak
    window only; `recording_start` is the zero of the recording's clock on the container clock.
    Without them the whole recording is judged as before.

    The extracted WAV lives in a temporary folder that is always deleted afterwards, whether the
    run passes, fails or raises. Never raises.
    """
    try:
        upload_dir = Path(settings.UPLOAD_TEMP_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=upload_dir, prefix="audio_") as workdir:
            prepared = _prepare_wav(Path(media_path), Path(workdir), phases, recording_start)
            if prepared.failure is not None:
                return prepared.failure
            return _run_checks(prepared, challenge_phrase, lip_openness_data)
    except Exception as e:  # noqa: BLE001 - a detector must never raise
        logger.exception("Unexpected error in process_audio_pipeline")
        return _failure(
            f"Audio pipeline failed with unexpected error: {type(e).__name__}: {e}",
            f"{type(e).__name__}: {e}",
        )
