---
description: Run the recordings of one evaluation scenario through the analysis and append honest results to a CSV.
argument-hint: "<scenario number or name> <folder of recordings>"
allowed-tools: Read, Grep, Glob, Bash
---

Arguments: `$ARGUMENTS` - a scenario (see `.claude/context/audio-pipeline/test-scenarios.md` for the audio ones) and a folder of recordings. If either is missing, ask; do not guess.

1. Read the scenario's expected result from `test-scenarios.md`. For scenario 8 (synthetic voice saying the correct phrase) the phrase check may legitimately pass; report the actual result, do not treat a pass as a bug to hide.
2. For each recording call `orchestrator.analyze_media(path, visual_challenge, phrase)` (see `backend/tools/measure_clips.py` for how) and record: file, each signal's score and passed, the fused verdict, which check stopped it, and the time.
3. Append one row per recording to `backend/eval/results.csv` (create it with a header row if missing), tagged with the scenario and a UTC timestamp. Never overwrite or delete earlier rows.
4. Summarise how many recordings matched the expected result and whether each miss looks like a threshold question (worth `/threshold-sweep`) or a code bug. Never edit the expected-result column of `test-scenarios.md` to match what happened.

Output: a per-recording table and a scenario line such as "7/10 matched the expected result".
