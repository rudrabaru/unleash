"""
Run every clip in a manifest through the full analysis and print one row per clip: the score
of each signal, the fused verdict and the time taken. Use it to re-measure the detectors after
a change; the default manifest (eval/manifest.json) lists the real-face sample clips.

Usage (from backend/):
    .venv\\Scripts\\python.exe tools/measure_clips.py [--manifest eval/manifest.json]
                                                     [--phrase "w1 w2 w3 w4 w5"] [--json out.json]

Clips without the spoken phrase simply fail the audio check; the video signals are still measured.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app import orchestrator  # noqa: E402

DEFAULT_PHRASE = "walnut lantern bicycle maple trumpet"
SIGNALS = ("audio_pipeline", "visual_liveness", "visual_challenge", "deepfake", "replay")
HEADERS = ("clip", "challenge", "audio", "liveness", "challenge", "deepfake", "replay", "verdict", "score", "secs")


def _cell(result: Dict[str, Any]) -> str:
    if result["error"] is not None:
        return "error"
    score = "-" if result["score"] is None else f"{result['score']:.2f}"
    return f"{score}{'' if result['passed'] else ' x'}"


def measure(manifest_path: Path, phrase: str) -> List[Dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = []
    for clip in manifest["clips"]:
        path = BACKEND / clip["path"]
        started = time.perf_counter()
        analysis = orchestrator.analyze_media(path, clip["visual_challenge"], phrase)
        rows.append({
            "clip": clip["path"],
            "kind": clip["kind"],
            "visual_challenge": clip["visual_challenge"],
            "verdict": analysis.fusion.status.value,
            "confidence": analysis.fusion.confidence,
            "reason": analysis.fusion.reason,
            "seconds": round(time.perf_counter() - started, 1),
            "signals": {name: analysis.signals[name].model_dump() for name in SIGNALS},
        })
    return rows


def print_table(rows: List[Dict[str, Any]]) -> None:
    table = [HEADERS]
    for row in rows:
        results = row["signals"]
        table.append((
            Path(row["clip"]).name,
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
    parser.add_argument("--phrase", default=DEFAULT_PHRASE, help="the 5-word challenge the audio is checked against")
    parser.add_argument("--json", type=Path, help="also write the full results to this file")
    args = parser.parse_args()

    rows = measure(args.manifest, args.phrase)
    print_table(rows)
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
