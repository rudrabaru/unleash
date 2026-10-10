"""The calibration helper: file-name parsing and manifest updates."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from add_clips import add_clips, parse_clip_name  # noqa: E402

GOOD = "clip-TURN_HEAD_LEFT-paddle_envelope_carpet_dolphin_quarry-1791282202499.webm"


def test_parses_the_action_and_the_phrase_from_a_recorder_name():
    assert parse_clip_name(GOOD) == {"visual_challenge": "TURN_HEAD_LEFT", "phrase": "paddle envelope carpet dolphin quarry"}


def test_rejects_names_that_do_not_fit():
    assert parse_clip_name("clip-LOOK_DOWN-1791282202499.webm") is None  # an older name without the words
    assert parse_clip_name("clip-SPIN-a_b_c_d_e-1.webm") is None
    assert parse_clip_name("holiday.webm") is None


def test_adds_copies_and_does_not_duplicate(tmp_path):
    source = tmp_path / "downloads"
    source.mkdir()
    (source / GOOD).write_bytes(b"x")
    (source / "clip-LOOK_DOWN-1.webm").write_bytes(b"x")
    manifest, recordings = tmp_path / "calibration.json", tmp_path / "recordings"

    first = add_clips([source], "genuine", "front light", manifest, recordings)
    assert first["added"] == [GOOD] and len(first["skipped"]) == 1
    assert (recordings / GOOD).exists()

    second = add_clips([source], "genuine", "front light", manifest, recordings)
    assert second["added"] == [] and second["already_listed"] == [GOOD]

    clips = json.loads(manifest.read_text(encoding="utf-8"))["clips"]
    assert all(clip["protocol"] is True for clip in clips)  # recorder clips are judged against the windows
    assert len(clips) == 1
    assert clips[0]["kind"] == "genuine" and clips[0]["phrase"] == "paddle envelope carpet dolphin quarry"
