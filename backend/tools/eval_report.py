"""
Read eval/features.jsonl (written by dump_features.py) and print what the recordings show, as counts
with exact intervals, never as a single certified percentage:

1. Verdicts per kind of clip. Genuine clips: how many reached VERIFIED. Every other kind is an attack
   or a failed challenge: how many were wrongly VERIFIED, with the 95% upper bound (31% at 8 clips, 18%
   at 15, 9.5% at 30, 4.9% at 60: "FAR below 5%" needs about 60 clips of a kind). RETRY is shown apart
   and left out of the rates: the recording could not be judged.
2. Each signal against the attacks it is meant to catch: how often it has a score on genuine takes,
   and the AUC (chance that a genuine score is above an attack score) with a speaker-cluster interval.
3. The rule for leaving report-only (V1_RELEASE_PLAN.md), applied mechanically.

Usage (from backend/):
    .venv\\Scripts\\python.exe tools/eval_report.py [--features eval/features.jsonl] [--json report.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_stats import clopper_pearson, cluster_bootstrap_auc, zero_event_upper  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent
GENUINE = "genuine"
VERDICTS = ("VERIFIED", "SUSPICIOUS", "FAILED", "RETRY")

# The attacks each signal is meant to catch (the plan's definition, not a result). A signal that is
# never shown to separate its own targets stays report-only.
SIGNAL_TARGETS = {
    "visual_liveness": ("photo", "replay"),
    "deepfake": ("face_swap",),
    "replay": ("replay", "photo"),
    "voice_authenticity": ("synthetic_voice", "audio_replay"),
    "lip_sync": ("synthetic_voice", "audio_replay", "photo"),
}

# The rule for leaving report-only: every line must hold.
MIN_AUC_LOWER = 0.70
MIN_AUC_LOWER_PER_STRATUM = 0.60
MIN_GENUINE_COVERAGE = 0.90


def load_records(path: Path) -> List[Dict[str, Any]]:
    """The latest line per clip (a clip analysed again by newer code replaces its older line)."""
    latest: Dict[str, Dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            latest[record["id"]] = record
    return list(latest.values())


def signal_score(record: Dict[str, Any], signal: str) -> Optional[float]:
    """One signal's score for a clip, or None if it had none (an error or too little to judge)."""
    signals = record["signals"]
    if signal == "voice_authenticity":
        value = (signals["audio_pipeline"].get("details") or {}).get("voice_authenticity_score")
    elif signal == "lip_sync":
        value = (signals["audio_pipeline"].get("details") or {}).get("av_alignment_score")
    else:
        result = signals[signal]
        value = None if result.get("error") else result.get("score")
    return None if value is None else float(value)


def verdict_table(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    table: Dict[str, Dict[str, Any]] = {}
    by_kind = defaultdict(list)
    for record in records:
        by_kind[record["kind"]].append(record)
    for kind, items in sorted(by_kind.items()):
        counts = Counter(r["verdict"] for r in items)
        judged = len(items) - counts["RETRY"]
        accepted = counts["VERIFIED"]
        entry: Dict[str, Any] = {"clips": len(items), **{v: counts[v] for v in VERDICTS}, "judged": judged}
        if judged:
            low, high = clopper_pearson(accepted, judged)
            entry["verified_rate_interval"] = [round(low, 3), round(high, 3)]
            if kind != GENUINE:
                entry["false_accept_upper_95"] = round(clopper_pearson(accepted, judged, one_sided=True)[1], 3)
                entry["zero_accepts_upper_95_at_this_n"] = round(zero_event_upper(judged), 3)
        table[kind] = entry
    return table


def _auc_rows(records: List[Dict[str, Any]], signal: str, targets) -> List[tuple]:
    rows = []
    for record in records:
        if record["kind"] != GENUINE and record["kind"] not in targets:
            continue
        score = signal_score(record, signal)
        if score is not None:
            rows.append((record.get("speaker", ""), record["kind"] == GENUINE, score))
    return rows


def signal_table(records: List[Dict[str, Any]], resamples: int = 2000) -> Dict[str, Dict[str, Any]]:
    genuine = [r for r in records if r["kind"] == GENUINE]
    table: Dict[str, Dict[str, Any]] = {}
    for signal, targets in SIGNAL_TARGETS.items():
        scored = [r for r in genuine if signal_score(r, signal) is not None]
        coverage = len(scored) / len(genuine) if genuine else None
        rows = _auc_rows(records, signal, targets)
        stats = cluster_bootstrap_auc(rows, resamples=resamples)
        attack_clips = sum(1 for _, is_genuine, _ in rows if not is_genuine)

        strata: Dict[str, Optional[float]] = {}
        for field in ("device", "lighting"):
            for value in sorted({r.get(field) for r in records if r.get(field)}):
                subset = [r for r in records if r.get(field) == value]
                sub_rows = _auc_rows(subset, signal, targets)
                if any(g for _, g, _ in sub_rows) and any(not g for _, g, _ in sub_rows):
                    strata[f"{field}={value}"] = cluster_bootstrap_auc(sub_rows, resamples=resamples)["lower_one_sided"]

        checks = {
            "auc_lower_bound_at_least_0.70": None if stats["lower_one_sided"] is None else stats["lower_one_sided"] >= MIN_AUC_LOWER,
            "held_out_log_loss_improves": None,  # needs the learned fusion (calibration package); not decidable yet
            "genuine_coverage_at_least_90%": None if coverage is None else coverage >= MIN_GENUINE_COVERAGE,
            "every_stratum_lower_bound_at_least_0.60": (
                None if not strata or any(v is None for v in strata.values()) else all(v >= MIN_AUC_LOWER_PER_STRATUM for v in strata.values())
            ),
        }
        table[signal] = {
            "targets": list(targets),
            "genuine_with_score": f"{len(scored)}/{len(genuine)}",
            "attack_clips_scored": attack_clips,
            "auc": stats["auc"],
            "auc_interval": [stats["low"], stats["high"]],
            "auc_lower_one_sided": stats["lower_one_sided"],
            "clustered_by_speaker": bool(stats["clustered"]),
            "strata_lower_bounds": strata,
            "leave_report_only": checks,
            "may_leave_report_only": all(v is True for v in checks.values()),
        }
    return table


def build_report(records: List[Dict[str, Any]], resamples: int = 2000) -> Dict[str, Any]:
    return {
        "clips": len(records),
        "speakers": sorted({r.get("speaker") for r in records if r.get("speaker")}),
        "git_commits": sorted({r.get("git_commit", "?") for r in records}),
        "verdicts": verdict_table(records),
        "signals": signal_table(records, resamples),
    }


def _fmt(value: Optional[float]) -> str:
    return "-" if value is None else f"{value:.2f}"


def print_report(report: Dict[str, Any]) -> None:
    print(f"{report['clips']} clips, speakers: {', '.join(report['speakers']) or 'not recorded'}; code: {', '.join(report['git_commits'])}\n")
    print("VERDICTS (RETRY is not judged and is left out of the intervals)")
    print(f"{'kind':18s} {'clips':>5s} {'VERIF':>5s} {'SUSP':>5s} {'FAIL':>5s} {'RETRY':>5s}  verified rate (95% interval)   wrongly verified: upper 95%")
    for kind, row in report["verdicts"].items():
        interval = row.get("verified_rate_interval")
        text = "-" if not interval else f"{interval[0]:.2f}-{interval[1]:.2f}"
        upper = row.get("false_accept_upper_95")
        extra = "" if upper is None else f"{upper:.2f}  (zero accepts would give {row['zero_accepts_upper_95_at_this_n']:.2f} at n={row['judged']})"
        print(f"{kind:18s} {row['clips']:5d} {row['VERIFIED']:5d} {row['SUSPICIOUS']:5d} {row['FAILED']:5d} {row['RETRY']:5d}  {text:28s}   {extra}")

    print("\nSIGNALS against the attacks they target (AUC 0.5 = no separation, 1.0 = perfect)")
    for name, row in report["signals"].items():
        lower = row["auc_lower_one_sided"]
        print(f"\n{name}  targets: {', '.join(row['targets'])}")
        print(f"  genuine takes with a score: {row['genuine_with_score']}; attack clips scored: {row['attack_clips_scored']}")
        interval = "no interval" if row["auc_interval"][0] is None else f"interval {_fmt(row['auc_interval'][0])}-{_fmt(row['auc_interval'][1])}"
        print(f"  AUC {_fmt(row['auc'])}, {interval}, lower bound {_fmt(lower)}"
              f"{'' if row['clustered_by_speaker'] else '  (one speaker only: resampled by clip, not by person)'}")
        for check, ok in row["leave_report_only"].items():
            print(f"  [{'pass' if ok else 'FAIL' if ok is False else 'open'}] {check}")
        print(f"  -> {'may leave report-only' if row['may_leave_report_only'] else 'stays report-only'}")
    print("\n'open' means there is not yet enough data (or, for log-loss, no learned fusion) to decide.")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--features", type=Path, default=BACKEND / "eval" / "features.jsonl")
    parser.add_argument("--json", type=Path, help="also write the report to this file")
    parser.add_argument("--resamples", type=int, default=2000)
    args = parser.parse_args(argv)
    if not args.features.exists():
        raise SystemExit(f"{args.features} not found: run tools/dump_features.py first")
    report = build_report(load_records(args.features), args.resamples)
    print_report(report)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
