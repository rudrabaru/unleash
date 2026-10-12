"""The evaluation tools: statistics against known values, the report on made-up records, the feature dump and the campaign checklist."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import dump_features  # noqa: E402
import eval_report  # noqa: E402
import trial_plan  # noqa: E402
from eval_stats import auc, clopper_pearson, cluster_bootstrap_auc, zero_event_upper  # noqa: E402


# --- statistics ----------------------------------------------------------------------------------

@pytest.mark.parametrize("trials, expected", [(8, 0.3123), (15, 0.1810), (30, 0.0950), (60, 0.0487)])
def test_zero_event_upper_bound_matches_the_figures_in_the_plan(trials, expected):
    assert zero_event_upper(trials) == pytest.approx(expected, abs=5e-4)
    assert clopper_pearson(0, trials, one_sided=True)[1] == pytest.approx(expected, abs=5e-4)


def test_clopper_pearson_two_sided_known_values():
    low, high = clopper_pearson(5, 10)
    assert (low, high) == (pytest.approx(0.1871, abs=5e-4), pytest.approx(0.8129, abs=5e-4))
    assert clopper_pearson(3, 3)[0] == pytest.approx(0.025 ** (1 / 3), abs=1e-6)  # all successes: the upper end is 1
    assert clopper_pearson(3, 3)[1] == 1.0
    assert clopper_pearson(0, 5)[0] == 0.0


def test_clopper_pearson_refuses_impossible_counts():
    with pytest.raises(ValueError):
        clopper_pearson(4, 3)
    with pytest.raises(ValueError):
        clopper_pearson(0, 0)


def test_auc_counts_ties_as_half_and_needs_both_sides():
    assert auc([0.9, 0.8], [0.1, 0.8]) == pytest.approx(0.875)
    assert auc([0.2], [0.9]) == 0.0
    assert auc([], [0.5]) is None and auc([0.5], []) is None


def test_bootstrap_of_a_perfect_separation_has_a_perfect_lower_bound():
    rows = [(s, True, 0.9) for s in "ABC" for _ in range(3)] + [(s, False, 0.1) for s in "ABC" for _ in range(3)]
    result = cluster_bootstrap_auc(rows, resamples=200)
    assert result["auc"] == 1.0 and result["lower_one_sided"] == 1.0 and result["clustered"] == 1.0


def test_bootstrap_of_scores_that_do_not_separate_stays_near_chance_and_is_wide():
    rows = [(s, g, 0.5) for s in "ABC" for g in (True, False) for _ in range(4)]
    result = cluster_bootstrap_auc(rows, resamples=200)
    assert result["auc"] == 0.5 and result["lower_one_sided"] <= 0.5


def test_bootstrap_with_one_speaker_says_it_could_not_cluster():
    rows = [("A", True, 0.9)] * 4 + [("A", False, 0.1)] * 4
    assert cluster_bootstrap_auc(rows, resamples=50)["clustered"] == 0.0


# --- the report ----------------------------------------------------------------------------------

def _record(clip_id, kind, speaker, verdict, replay=None, voice=None, device="laptop", lighting="front"):
    def result(score):
        return {"score": score, "passed": True, "reason": "x", "error": None if score is not None else "no data", "details": {}}

    return {
        "id": clip_id, "kind": kind, "speaker": speaker, "device": device, "lighting": lighting,
        "verdict": verdict, "git_commit": "abc123",
        "signals": {
            "audio_pipeline": {**result(None), "error": None, "details": {"voice_authenticity_score": voice, "av_alignment_score": None}},
            "visual_liveness": result(0.9), "visual_challenge": result(1.0), "deepfake": result(None), "replay": result(replay),
        },
    }


def _records():
    records = []
    for i, speaker in enumerate("ABC"):
        for j in range(4):
            records.append(_record(f"g{i}{j}", "genuine", speaker, "VERIFIED", replay=0.9, voice=0.8))
        records.append(_record(f"p{i}", "replay", speaker, "FAILED", replay=0.2))
        records.append(_record(f"r{i}", "replay", speaker, "RETRY"))
        records.append(_record(f"s{i}", "synthetic_voice", speaker, "VERIFIED", replay=0.9, voice=0.79))
    return records


def test_verdict_table_counts_retry_apart_and_bounds_the_wrongly_accepted():
    table = eval_report.verdict_table(_records())
    assert table["genuine"]["VERIFIED"] == 12 and table["genuine"]["judged"] == 12
    assert table["replay"]["RETRY"] == 3 and table["replay"]["judged"] == 3  # RETRY is not a judged clip
    assert table["synthetic_voice"]["false_accept_upper_95"] > 0.5  # 3 of 3 wrongly verified
    assert table["replay"]["false_accept_upper_95"] == pytest.approx(zero_event_upper(3), abs=1e-3)  # none wrongly verified


def test_a_signal_that_separates_may_leave_report_only_only_when_every_rule_holds():
    report = eval_report.build_report(_records(), resamples=300)
    replay = report["signals"]["replay"]
    assert replay["auc"] == 1.0 and replay["genuine_with_score"] == "12/12"
    assert replay["leave_report_only"]["auc_lower_bound_at_least_0.70"] is True
    assert replay["leave_report_only"]["held_out_log_loss_improves"] is None  # needs the learned fusion
    assert replay["may_leave_report_only"] is False  # an open rule keeps it report-only

    voice = report["signals"]["voice_authenticity"]  # 0.8 against 0.79 in every pair: separates, but barely, and still open
    assert voice["auc"] == 1.0


def test_a_signal_with_no_scores_cannot_leave_report_only():
    deepfake = eval_report.build_report(_records(), resamples=50)["signals"]["deepfake"]
    assert deepfake["auc"] is None and deepfake["genuine_with_score"] == "0/12"
    assert deepfake["leave_report_only"]["genuine_coverage_at_least_90%"] is False
    assert deepfake["may_leave_report_only"] is False


def test_the_newest_line_for_a_clip_wins(tmp_path):
    older, newer = _record("same", "genuine", "A", "FAILED"), _record("same", "genuine", "A", "VERIFIED")
    path = tmp_path / "f.jsonl"
    path.write_text(json.dumps(older) + "\n" + json.dumps(newer) + "\n", encoding="utf-8")
    assert [r["verdict"] for r in eval_report.load_records(path)] == ["VERIFIED"]


def test_printing_the_report_does_not_crash(capsys):
    eval_report.print_report(eval_report.build_report(_records(), resamples=50))
    assert "stays report-only" in capsys.readouterr().out


# --- the feature dump ----------------------------------------------------------------------------

def test_dump_writes_one_line_per_clip_without_speech_and_resumes(tmp_path, monkeypatch):
    clip_file = dump_features.BACKEND / "eval" / "_dump_test.bin"
    clip_file.write_bytes(b"not really a video")
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"clips": [
        {"path": "eval/_dump_test.bin", "kind": "genuine", "speaker": "A", "visual_challenge": "LOOK_UP", "protocol": True},
        {"path": "eval/does_not_exist.webm", "kind": "replay", "visual_challenge": "LOOK_UP"},
    ]}), encoding="utf-8")
    calls = []

    def fake_measure(clip, path, phrase):
        calls.append(path)
        signals = {"audio_pipeline": {"score": None, "passed": True, "reason": "r", "error": None,
                                      "details": {"transcript": "hello", "match_count": 4, "words_detected": ["hello"]}}}
        return {"verdict": "VERIFIED", "confidence": 0.9, "reason": "ok", "seconds": 1.0, "signals": signals}

    monkeypatch.setattr(dump_features.measure_clips, "_measure_one", fake_measure)
    out = tmp_path / "features.jsonl"
    try:
        assert dump_features.dump(manifest, out, "a b c d e") == {"written": 1, "already_done": 0, "missing": 1}
        record = json.loads(out.read_text(encoding="utf-8"))
        assert record["id"] == dump_features.sha256_of(clip_file) and record["speaker"] == "A"
        assert record["signals"]["audio_pipeline"]["details"] == {"match_count": 4}  # what was said is gone
        assert record["protocol_version"] == dump_features.PROTOCOL_V1.version

        assert dump_features.dump(manifest, out, "a b c d e")["already_done"] == 1  # resumes, does not analyse again
        assert len(calls) == 1
        assert dump_features.dump(manifest, out, "a b c d e", force=True)["written"] == 1
    finally:
        clip_file.unlink()


# --- the campaign checklist ----------------------------------------------------------------------

def test_trial_plan_counts_what_is_missing_and_where_the_bound_stands(tmp_path):
    manifest = tmp_path / "c.json"
    manifest.write_text(json.dumps({"clips": [
        {"kind": "genuine", "speaker": "A"}, {"kind": "genuine", "speaker": "B"}, {"kind": "genuine"},
        *[{"kind": "photo"} for _ in range(8)], {"kind": "something_new"},
    ]}), encoding="utf-8")
    report = trial_plan.status(manifest)
    assert report["kinds"]["genuine"]["have"] == 3 and report["kinds"]["genuine"]["missing"] == 69
    assert report["kinds"]["photo"]["zero_accepts_upper_95_now"] == pytest.approx(0.312, abs=1e-3)
    assert report["kinds"]["replay"]["have"] == 0 and report["genuine_per_speaker"]["(not recorded)"] == 1
    assert report["other_kinds"] == ["something_new"]
    assert sum(trial_plan.TARGETS.values()) >= 270  # about 300 clips in all


def test_trial_plan_works_before_any_clip_exists(tmp_path):
    assert trial_plan.status(tmp_path / "none.json")["kinds"]["genuine"]["have"] == 0
