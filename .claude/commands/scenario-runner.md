---
description: Run a named audio test scenario's recordings through the module and append honest results to a CSV — the Phase 4 evaluation workhorse.
argument-hint: "<scenario number or name> <path to folder of recordings>"
allowed-tools: Read, Grep, Glob, Bash
---

You are running the **test scenario executor** for Phase 4 evaluation (Days 31–40), and usable earlier for the integration checklist's "tested against ≥3 of the 10 scenarios" requirement.

Arguments: `$ARGUMENTS` — expected as a scenario number/name and a folder of recordings (e.g. `4 backend/tests/fixtures/scenario_4/`). If either is missing, ask for it rather than guessing which scenario or which files were meant.

## Before running

Read `.claude/context/audio-pipeline/test-scenarios.md` in full — it has the authoritative scenario table and, critically, the **honesty requirement** for scenario 8 (TTS injection): Stage 2 may legitimately pass on that scenario (the correct digits were said), and this command must report that honestly rather than treating a Stage 2 pass as a bug to hide.

## What to do

1. Identify the requested scenario's expected result from `test-scenarios.md`.
2. For each recording in the given folder, run it through the current audio module and record: filename, `score`, `passed`, `reason`, which stage (if any) caused a gate failure, and elapsed time.
3. Append these rows to `.claude/context/audio-pipeline/eval-results.csv` (create it with a header row if it doesn't exist yet), tagged with the scenario number/name and a UTC timestamp for this run. **Never overwrite or delete prior rows** — this file is an append-only evaluation log across the whole Phase 4 effort.
4. Summarize: how many of the recordings matched the scenario's expected result, and — for any that didn't — whether that looks like a genuine threshold-tuning signal (worth flagging for `/threshold-sweep`) or a code bug.

## Output format

A per-recording table plus a scenario-level summary line (e.g. "7/10 matched expected result"). End with an explicit honesty check: if this was scenario 8, state the actual Stage 2 and Stage 3 outcomes plainly, without editorializing them into a pass/fail framing the scenario table doesn't ask for. Do not edit `test-scenarios.md`'s expected-result column to match what happened — that column is the spec, not a log.
