"""
The calibration campaign as a checklist: how many clips of each kind the plan asks for (V1_RELEASE_PLAN.md,
P2), how many are in the calibration manifest, and what is still missing. It also shows what the clips
so far can and cannot prove: with zero wrongly accepted clips the 95% upper bound on the false-accept
rate is still 31% at 8 clips and only drops below 5% at about 60.

Usage (from backend/):
    .venv\\Scripts\\python.exe tools/trial_plan.py [--manifest eval/calibration.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_stats import zero_event_upper  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent

# What to record, per kind (`add_clips.py --kind`). Genuine: 3 speakers x 2 conditions x 4 actions x 3 repeats.
# Replay is half phone screen, half monitor (say which in --performed). About 300 clips in all.
TARGETS: Dict[str, int] = {
    "genuine": 72,
    "no_action": 30,
    "replay": 60,
    "photo": 30,
    "synthetic_voice": 30,
    "audio_replay": 15,
    "wrong_phrase": 15,
    "silence": 15,
    "wrong_direction": 15,
}
GENUINE_PER_SPEAKER = 24
SPEAKERS = 3

HOW = {
    "genuine": "do exactly what the screen asks; 2 lighting conditions, all 4 actions (left, right, up, down), 3 repeats each",
    "no_action": "read and speak the words but look at the screen and do not do the movement",
    "replay": "play a genuine take (same speakers) on a phone screen (30) and on a monitor (30) in front of the camera",
    "photo": "a printed or on-screen photo of the face in front of the camera, a live voice reading the words",
    "synthetic_voice": "text-to-speech reading the words over a live face",
    "audio_replay": "a recording of the speaker's voice played through a loudspeaker over a live face",
    "wrong_phrase": "say five other words",
    "silence": "do the movement but say nothing",
    "wrong_direction": "turn the other way",
}


def status(manifest_path: Path) -> Dict[str, object]:
    clips = json.loads(manifest_path.read_text(encoding="utf-8"))["clips"] if manifest_path.exists() else []
    have = Counter(c["kind"] for c in clips)
    genuine_speakers = Counter(c.get("speaker") or "(not recorded)" for c in clips if c["kind"] == "genuine")
    rows = {
        kind: {"target": target, "have": have[kind], "missing": max(0, target - have[kind]),
               "zero_accepts_upper_95_now": None if kind == "genuine" or not have[kind] else round(zero_event_upper(have[kind]), 3)}
        for kind, target in TARGETS.items()
    }
    return {"kinds": rows, "genuine_per_speaker": dict(genuine_speakers), "other_kinds": sorted(set(have) - set(TARGETS))}


def print_status(report: Dict[str, object]) -> None:
    print(f"{'kind':16s} {'have':>5s} {'target':>6s} {'missing':>7s}  false-accept upper bound if none got through   how")
    for kind, row in report["kinds"].items():
        bound = "-" if row["zero_accepts_upper_95_now"] is None else f"{row['zero_accepts_upper_95_now']:.2f}"
        print(f"{kind:16s} {row['have']:5d} {row['target']:6d} {row['missing']:7d}  {bound:>10s}{'':26s} {HOW[kind]}")
    total_have = sum(r["have"] for r in report["kinds"].values())
    print(f"\n{total_have} of {sum(TARGETS.values())} clips.")
    speakers = report["genuine_per_speaker"]
    print("genuine clips per speaker (aim for %d each, at least %d speakers): %s" % (
        GENUINE_PER_SPEAKER, SPEAKERS, ", ".join(f"{s}: {n}" for s, n in sorted(speakers.items())) or "none yet"))
    if report["other_kinds"]:
        print(f"kinds in the manifest that the plan does not count: {', '.join(report['other_kinds'])}")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=BACKEND / "eval" / "calibration.json")
    print_status(status(parser.parse_args(argv).manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
