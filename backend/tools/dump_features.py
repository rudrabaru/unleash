"""
Run every clip of a manifest through the full analysis once and append one JSON line per clip to
eval/features.jsonl. Everything the evaluation needs later (calibration, fusion, the report) is read
from that file, so changing a threshold or the fusion never means analysing the recordings again
(about 10 s a clip).

A line holds: the clip's content hash (its id: a re-recorded or renamed file is recognised), the manifest
fields (kind, speaker, device, lighting, challenge), the verdict, every signal's result with its details,
the time taken, and which code produced it (git commit, phase protocol version). What the person said
is removed from the details, as it is from a stored session. A clip already in the file under the same
hash and the same git commit is skipped, so an interrupted run resumes; `--force` redoes everything.

Usage (from backend/):
    .venv\\Scripts\\python.exe tools/dump_features.py --manifest eval/calibration.json [--out eval/features.jsonl] [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import measure_clips  # noqa: E402  (the one place that knows how to analyse a manifest entry)
from app.db import _SPOKEN_CONTENT_KEYS  # noqa: E402
from app.protocol import PROTOCOL_V1  # noqa: E402

DEFAULT_OUT = BACKEND / "eval" / "features.jsonl"
MANIFEST_FIELDS = ("kind", "speaker", "device", "lighting", "browser", "performed", "visual_challenge", "phrase", "protocol", "mirrored")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=BACKEND, capture_output=True, text=True, check=True)
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "app"], cwd=BACKEND, capture_output=True, text=True, check=True).stdout.strip()
        return out.stdout.strip() + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def without_speech(signals: Dict[str, Any]) -> Dict[str, Any]:
    """The signals with what was said taken out of every details block."""
    cleaned = {}
    for name, result in signals.items():
        details = {k: v for k, v in (result.get("details") or {}).items() if k not in _SPOKEN_CONTENT_KEYS}
        cleaned[name] = {**result, "details": details}
    return cleaned


def load_done(out_path: Path) -> Set[Tuple[str, str]]:
    """(content hash, git commit) pairs already in the output file."""
    if not out_path.exists():
        return set()
    done = set()
    for line in out_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            done.add((record["id"], record["git_commit"]))
    return done


def dump(manifest_path: Path, out_path: Path, phrase: str, force: bool = False) -> Dict[str, int]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    commit = git_commit()
    done = set() if force else load_done(out_path)
    counts = {"written": 0, "already_done": 0, "missing": 0}
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="dump_features_") as scratch, out_path.open("a", encoding="utf-8") as out:
        for clip in manifest["clips"]:
            path = BACKEND / clip["path"]
            if not path.exists():
                print(f"skipped (file missing): {clip['path']}", file=sys.stderr)
                counts["missing"] += 1
                continue
            clip_id = sha256_of(path)
            if (clip_id, commit) in done:
                counts["already_done"] += 1
                continue
            row = measure_clips._measure_one(clip, measure_clips._unmirrored_copy(path, Path(scratch)) if clip.get("mirrored") else path, phrase)
            record = {
                "id": clip_id,
                "path": clip["path"],
                **{field: clip[field] for field in MANIFEST_FIELDS if field in clip},
                "git_commit": commit,
                "protocol_version": PROTOCOL_V1.version if clip.get("protocol") else None,
                "verdict": row["verdict"],
                "confidence": row["confidence"],
                "reason": row["reason"],
                "seconds": row["seconds"],
                "signals": without_speech(row["signals"]),
            }
            out.write(json.dumps(record) + "\n")
            out.flush()
            counts["written"] += 1
            print(f"{counts['written']:4d}  {Path(clip['path']).name}  {row['verdict']}", flush=True)
    return counts


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=BACKEND / "eval" / "calibration.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--phrase", default=measure_clips.DEFAULT_PHRASE, help="the 5-word challenge for clips that do not list their own")
    parser.add_argument("--force", action="store_true", help="analyse every clip again even if it is already in the file")
    args = parser.parse_args(argv)
    counts = dump(args.manifest, args.out, args.phrase, args.force)
    print(f"\n{counts['written']} written, {counts['already_done']} already done, {counts['missing']} missing -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
