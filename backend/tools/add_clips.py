"""
Add recorder clips to the calibration manifest, reading the action and the 5 words from the
file name the recorder page gives them: clip-<ACTION>-<word1_word2_word3_word4_word5>-<time>.webm

The clips are copied to eval/recordings/ and listed in eval/calibration.json. Both are ignored by
git (they show people's faces and voices); the committed sample set stays in eval/manifest.json.
Measure them with:  python tools/measure_clips.py --manifest eval/calibration.json

Every clip is listed with "protocol": true: a recorder clip follows the read/speak/act protocol, so
measure_clips judges it against the windows, as a session does. `--speaker` and `--device` are kept
with each clip because the calibration is only meaningful per speaker and per camera.

Usage (from backend/):
    .venv\\Scripts\\python.exe tools/add_clips.py D:\\Downloads --kind genuine --speaker A --device laptop --performed "front light"
    .venv\\Scripts\\python.exe tools/add_clips.py clip-LOOK_UP-a_b_c_d_e-1.webm --kind replay --performed "phone screen"

`--kind` is what the clip is, not what you expect the system to say: genuine, replay, photo,
synthetic_voice, wrong_phrase, silence, wrong_direction. For wrong_phrase and silence the file
name still carries the words the session asked for, which is what the check is measured against.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND = Path(__file__).resolve().parent.parent
RECORDINGS = BACKEND / "eval" / "recordings"
CALIBRATION_MANIFEST = BACKEND / "eval" / "calibration.json"

KINDS = ("genuine", "replay", "photo", "synthetic_voice", "wrong_phrase", "silence", "wrong_direction")
ACTIONS = ("TURN_HEAD_LEFT", "TURN_HEAD_RIGHT", "LOOK_UP", "LOOK_DOWN", "BLINK_TWICE")
_NAME = re.compile(r"^clip-(?P<action>[A-Z_]+)-(?P<words>[A-Za-z]+(?:_[A-Za-z]+){4})-(?P<stamp>\d+)\.webm$")


def parse_clip_name(name: str) -> Optional[Dict[str, str]]:
    """The visual action and the phrase encoded in a recorder file name, or None if it does not fit."""
    match = _NAME.match(name)
    if not match or match["action"] not in ACTIONS:
        return None
    return {"visual_challenge": match["action"], "phrase": match["words"].replace("_", " ").lower()}


def _find_clips(sources: List[Path]) -> List[Path]:
    found: List[Path] = []
    for source in sources:
        found.extend(sorted(source.glob("clip-*.webm")) if source.is_dir() else [source])
    return found


def add_clips(sources: List[Path], kind: str, performed: str, manifest_path: Path = CALIBRATION_MANIFEST,
              recordings_dir: Path = RECORDINGS, speaker: str = "", device: str = "") -> Dict[str, List[str]]:
    manifest: Dict[str, Any] = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {"description": "Local calibration clips recorded through the recorder page (not in git).", "clips": []}
    )
    known = {Path(c["path"]).name for c in manifest["clips"]}
    report: Dict[str, List[str]] = {"added": [], "already_listed": [], "skipped": []}

    for clip in _find_clips(sources):
        parsed = parse_clip_name(clip.name)
        if parsed is None:
            report["skipped"].append(f"{clip.name} (name is not clip-<ACTION>-<five_words>-<time>.webm)")
            continue
        if clip.name in known:
            report["already_listed"].append(clip.name)
            continue
        recordings_dir.mkdir(parents=True, exist_ok=True)
        destination = recordings_dir / clip.name
        if clip.resolve() != destination.resolve():
            shutil.copy2(clip, destination)
        manifest["clips"].append({
            "path": destination.relative_to(BACKEND).as_posix() if destination.is_relative_to(BACKEND) else str(destination),
            "kind": kind,
            "performed": performed,
            "protocol": True,
            **({"speaker": speaker} if speaker else {}),
            **({"device": device} if device else {}),
            **parsed,
        })
        known.add(clip.name)
        report["added"].append(clip.name)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="+", type=Path, help="clip files, or folders searched for clip-*.webm")
    parser.add_argument("--kind", required=True, choices=KINDS)
    parser.add_argument("--performed", default="", help="a short note: lighting, how the attack was made")
    parser.add_argument("--speaker", default="", help="who is in the clip (a letter or name; the calibration is leave-one-speaker-out)")
    parser.add_argument("--device", default="", help="the camera and browser used, e.g. 'laptop webcam, Chrome'")
    args = parser.parse_args()

    report = add_clips(args.sources, args.kind, args.performed, speaker=args.speaker, device=args.device)
    for label, names in report.items():
        for name in names:
            print(f"{label.replace('_', ' ')}: {name}")
    print(f"\n{len(report['added'])} added to {CALIBRATION_MANIFEST.relative_to(BACKEND)}")
    return 0 if not report["skipped"] else 1


if __name__ == "__main__":
    sys.exit(main())
