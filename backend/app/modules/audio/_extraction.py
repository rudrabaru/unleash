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

TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1
DEFAULT_TRUNCATION_RATIO = 0.5

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


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


def probe_media(path: Path | str, timeout: int = 30) -> Dict[str, Any]:
    """
    Probe container and stream information using ffprobe.
    Returns dict:
      {
        "ok": bool,
        "container": str | None,
        "duration": float | None,
        "video_codec": str | None,
        "audio": {"codec": str, "sample_rate": int, "channels": int} | None,
        "error": str | None
      }
    """
    path_obj = Path(path)
    if not path_obj.exists():
        return {
            "ok": False,
            "container": None,
            "duration": None,
            "video_codec": None,
            "audio": None,
            "error": f"File does not exist: {path}"
        }

    if not FFPROBE:
        return {
            "ok": False,
            "container": None,
            "duration": None,
            "video_codec": None,
            "audio": None,
            "error": "ffprobe executable not found on PATH"
        }

    argv = [
        FFPROBE,
        "-v", "error",
        "-show_streams",
        "-show_format",
        "-of", "json",
        str(path_obj)
    ]

    rc, out, err = run_command(argv, timeout=timeout)
    if rc != 0:
        return {
            "ok": False,
            "container": None,
            "duration": None,
            "video_codec": None,
            "audio": None,
            "error": err.strip() or f"ffprobe exited with rc={rc}"
        }

    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        return {
            "ok": False,
            "container": None,
            "duration": None,
            "video_codec": None,
            "audio": None,
            "error": f"Failed to parse ffprobe JSON output: {e}"
        }

    streams = data.get("streams", [])
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    
    format_info = data.get("format", {})
    raw_dur = format_info.get("duration")
    duration: Optional[float] = None
    if raw_dur not in (None, "N/A"):
        try:
            duration = float(raw_dur)
        except (ValueError, TypeError):
            duration = None

    audio_info: Optional[Dict[str, Any]] = None
    if audio_stream is not None:
        sr_raw = audio_stream.get("sample_rate")
        sample_rate = int(sr_raw) if sr_raw and str(sr_raw).isdigit() else None
        audio_info = {
            "codec": audio_stream.get("codec_name"),
            "sample_rate": sample_rate,
            "channels": audio_stream.get("channels")
        }

    return {
        "ok": True,
        "container": format_info.get("format_name"),
        "duration": duration,
        "video_codec": video_stream.get("codec_name") if video_stream else None,
        "audio": audio_info,
        "error": None
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

    if not FFMPEG:
        return False, "ffmpeg executable not found on PATH", 0.0

    dst.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    argv = [
        FFMPEG,
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
    Finding #2: An ffmpeg exit code 0 does not prove extraction completeness.
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
