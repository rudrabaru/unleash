"""
Run every clip in a manifest through the full analysis and print one row per clip: the score
of each signal, the fused verdict and the time taken. Use it to re-measure the detectors after
a change; the default manifest (eval/manifest.json) lists the real-face sample clips.

Usage (from backend/):
    .venv\\Scripts\\python.exe tools/measure_clips.py [--manifest eval/manifest.json]
                                                     [--phrase "w1 w2 w3 w4 w5"] [--json out.json]

A clip entry may carry its own "phrase"; otherwise --phrase is used. Clips that do not contain the
spoken phrase simply fail the audio check; the video signals are still measured. A listed file that
is missing (for example a local recording on another machine) is reported and skipped.

A clip entry with "protocol": true is judged against the read/speak/act windows, as a session is (it
must be a 13 s recording made with the recorder); without it the whole clip is judged.

A clip entry with "mirrored": true was saved as a mirror image (a selfie app shows your own left on
the left of the picture). The backend expects what a browser records, an unmirrored feed, so the tool
flips such a clip back into a temporary copy before analysing it. Browser recordings need no flag.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app import orchestrator  # noqa: E402
from app.protocol import PROTOCOL_V1  # noqa: E402

DEFAULT_PHRASE = "walnut lantern bicycle maple trumpet"
SIGNALS = ("audio_pipeline", "visual_liveness", "visual_challenge", "deepfake", "replay")
HEADERS = ("clip", "kind", "challenge", "audio", "liveness", "challenge", "deepfake", "replay", "verdict", "score", "secs")


def _cell(result: Dict[str, Any]) -> str:
    if result["error"] is not None:
        return "error"
    score = "-" if result["score"] is None else f"{result['score']:.2f}"
    return f"{score}{'' if result['passed'] else ' x'}"


def _unmirrored_copy(path: Path, folder: Path) -> Path:
    """A horizontally flipped copy of a mirror-image clip, i.e. what a browser would have recorded."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required to un-mirror clips marked \"mirrored\": true")
    out = folder / f"{path.stem}_unmirrored.webm"
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-vf", "hflip",
         "-c:v", "libvpx", "-b:v", "4M", "-c:a", "copy", str(out)],
        check=True,
    )
    return out


def measure(manifest_path: Path, phrase: str) -> List[Dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = []
    with tempfile.TemporaryDirectory(prefix="measure_clips_") as scratch:
        for clip in manifest["clips"]:
            path = BACKEND / clip["path"]
            if not path.exists():
                print(f"skipped (file missing): {clip['path']}", file=sys.stderr)
                continue
            if clip.get("mirrored"):
                path = _unmirrored_copy(path, Path(scratch))
            rows.append(_measure_one(clip, path, phrase))
    return rows


def _measure_one(clip: Dict[str, Any], path: Path, phrase: str) -> Dict[str, Any]:
    """Analyse one clip (`path` is the file to analyse, which may be an un-mirrored copy) and return its row."""
    started = time.perf_counter()
    phases = PROTOCOL_V1 if clip.get("protocol") else None
    analysis = orchestrator.analyze_media(path, clip["visual_challenge"], clip.get("phrase", phrase), phases=phases)
    return {
        "clip": clip["path"],
        "kind": clip["kind"],
        "visual_challenge": clip["visual_challenge"],
        "verdict": analysis.fusion.status.value,
        "confidence": analysis.fusion.confidence,
        "reason": analysis.fusion.reason,
        "seconds": round(time.perf_counter() - started, 1),
        "signals": {name: analysis.signals[name].model_dump() for name in SIGNALS},
    }


def print_table(rows: List[Dict[str, Any]]) -> None:
    table = [HEADERS]
    for row in rows:
        results = row["signals"]
        table.append((
            Path(row["clip"]).name,
            row["kind"],
            row["visual_challenge"],
            *(_cell(results[name]) for name in SIGNALS),
            row["verdict"],
            "-" if row["confidence"] is None else f"{row['confidence']:.2f}",
            f"{row['seconds']:.1f}",
        ))
    widths = [max(len(str(r[i])) for r in table) for i in range(len(HEADERS))]
    for r in table:
        print("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r)))
    print("\n'x' marks a signal whose own pass/fail check failed; 'error' marks a detector that could not measure.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=BACKEND / "eval" / "manifest.json")
    parser.add_argument("--phrase", default=DEFAULT_PHRASE, help="the 5-word challenge for clips that do not list their own")
    parser.add_argument("--json", type=Path, help="also write the full results to this file")
    args = parser.parse_args()

    rows = measure(args.manifest, args.phrase)
    print_table(rows)
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
