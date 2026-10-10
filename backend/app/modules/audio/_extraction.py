"""
Audio Extraction and Verification Subprocess Helpers.

Handles probing media containers and extracting 16kHz mono WAV audio
via ffmpeg and ffprobe subprocesses.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.modules.audio._constants import TARGET_CHANNELS, TARGET_SAMPLE_RATE

# ffmpeg can exit 0 and still lose most of the audio (seen on a clip cut off after 2 KB), so an
# extraction shorter than this share of the container's claimed duration counts as truncated.
DEFAULT_TRUNCATION_RATIO = 0.5

def _get_ffmpeg() -> str | None:
    return shutil.which("ffmpeg")

def _get_ffprobe() -> str | None:
    return shutil.which("ffprobe")


def run_command(argv: list[str], timeout: int = 120) -> tuple[int, str, str]:
    """
    Execute subprocess command safely with argv list, never shell=True.
    Returns (returncode, stdout, stderr), never raises.
    """
    try:
        p = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s: {' '.join(argv)}"
    except OSError as e:
        return -1, "", f"Subprocess OSError ({type(e).__name__}): {e}"
    except Exception as e:
        return -1, "", f"Unexpected error running command: {type(e).__name__}: {e}"


def _probe_failure(error: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "container": None,
        "duration": None,
        "video_codec": None,
        "audio": None,
        "error": error,
    }


def _parse_duration(format_info: Dict[str, Any]) -> Optional[float]:
    raw = format_info.get("duration")
    if raw in (None, "N/A"):
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _audio_info(audio_stream: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if audio_stream is None:
        return None
    sr_raw = audio_stream.get("sample_rate")
    try:
        audio_start = float(audio_stream.get("start_time"))
    except (TypeError, ValueError):
        audio_start = None
    return {
        "codec": audio_stream.get("codec_name"),
        "sample_rate": int(sr_raw) if sr_raw and str(sr_raw).isdigit() else None,
        "channels": audio_stream.get("channels"),
        # seconds on the container clock at which the audio track starts
        "start_time": audio_start,
    }


def probe_media(path: Path | str, timeout: int = 30) -> Dict[str, Any]:
    """
    Probe container and stream information using ffprobe.
    Returns dict:
      {
        "ok": bool,
        "container": str | None,
        "duration": float | None,
        "video_codec": str | None,
        "audio": {"codec": str, "sample_rate": int, "channels": int, "start_time": float | None} | None,
        "error": str | None
      }
    """
    path_obj = Path(path)
    if not path_obj.exists():
        return _probe_failure(f"File does not exist: {path}")
    ffprobe_path = _get_ffprobe()
    if not ffprobe_path:
        return _probe_failure("ffprobe executable not found on PATH")

    rc, out, err = run_command(
        [ffprobe_path, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path_obj)],
        timeout=timeout,
    )
    if rc != 0:
        return _probe_failure(err.strip() or f"ffprobe exited with rc={rc}")

    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        return _probe_failure(f"Failed to parse ffprobe JSON output: {e}")

    streams = data.get("streams", [])
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    format_info = data.get("format", {})
    return {
        "ok": True,
        "container": format_info.get("format_name"),
        "duration": _parse_duration(format_info),
        "video_codec": video_stream.get("codec_name") if video_stream else None,
        "audio": _audio_info(audio_stream),
        "error": None,
    }


def extract_wav(
    src_path: Path | str,
    dst_path: Path | str,
    timeout: int = 120
) -> Tuple[bool, Optional[str], float]:
    """
    Extract audio track from media file and resample to 16kHz mono PCM WAV.
    Forces output to 16kHz mono PCM (pcm_s16le).
    Returns (success, error_message, elapsed_seconds).
    """
    src = Path(src_path)
    dst = Path(dst_path)

    if not src.exists():
        return False, f"Source media file not found: {src}", 0.0

    ffmpeg_path = _get_ffmpeg()
    if not ffmpeg_path:
        return False, "ffmpeg executable not found on PATH", 0.0

    dst.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    argv = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(src),
        "-vn",                           # Drop video
        "-ac", str(TARGET_CHANNELS),     # Force mono
        "-ar", str(TARGET_SAMPLE_RATE),  # Force 16kHz
        "-c:a", "pcm_s16le",             # 16-bit PCM WAV
        "-f", "wav",
        str(dst)
    ]

    rc, _, err = run_command(argv, timeout=timeout)
    elapsed = time.perf_counter() - t0

    if rc != 0:
        return False, err.strip() or f"ffmpeg exited with rc={rc}", elapsed

    if not dst.exists() or dst.stat().st_size == 0:
        return False, "ffmpeg reported success but produced an empty or missing file", elapsed

    return True, None, elapsed


def verify_wav(path: Path | str) -> Tuple[bool, str]:
    """
    Verify that an output WAV file strictly satisfies the 16kHz mono contract.
    Returns (is_valid, description_or_error).
    """
    info = probe_media(path)
    if not info["ok"] or not info["audio"]:
        return False, f"Could not probe audio stream: {info.get('error') or 'no audio stream'}"

    a = info["audio"]
    sr = a.get("sample_rate")
    ch = a.get("channels")
    is_valid = (sr == TARGET_SAMPLE_RATE) and (ch == TARGET_CHANNELS)
    desc = f"codec={a.get('codec')}, rate={sr}Hz, channels={ch}"
    if not is_valid:
        return False, f"Resample contract violated (expected {TARGET_SAMPLE_RATE}Hz {TARGET_CHANNELS}ch, got {desc})"
    return True, desc


def check_extraction_completeness(
    claimed_duration: Optional[float],
    extracted_duration: Optional[float],
    threshold_ratio: float = DEFAULT_TRUNCATION_RATIO
) -> Tuple[bool, Optional[str]]:
    """
    An ffmpeg exit code 0 does not prove extraction completeness.
    Compares extracted duration against container's claimed duration.
    If container has no duration header (common in some browser MediaRecorder blobs),
    returns True (skips ratio check).
    If extracted duration is under threshold_ratio (default 50%) of claimed, flags as truncated.
    """
    if claimed_duration is None or claimed_duration <= 0:
        return True, None

    if extracted_duration is None:
        return False, "Extracted audio duration could not be determined"

    ratio = extracted_duration / claimed_duration
    if ratio < threshold_ratio:
        return False, (
            f"Extracted audio duration ({extracted_duration:.3f}s) is only {ratio * 100:.1f}% "
            f"of claimed container duration ({claimed_duration:.3f}s), below {threshold_ratio * 100:.0f}% threshold"
        )

    return True, None
