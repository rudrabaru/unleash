---
description: Run the full Stage-Level Integration Checklist against the current audio module state and report pass/fail per item — the "am I really done" gate before handing off to Dev 3's orchestrator.
argument-hint: "[optional: which stage or scope to focus on, e.g. 'Stage 1' or 'full module']"
allowed-tools: Read, Grep, Glob, Bash
---

You are running the **Stage-Level Integration Checklist** from `.claude/context/audio-pipeline/integration-checklist.md` against the current state of `backend/app/modules/audio/`. This is the gate that decides whether a stage (or the full audio module) is actually ready to hand off to Dev 3's orchestrator — do not rubber-stamp it.

Scope: `$ARGUMENTS` (default to evaluating the full audio module if nothing more specific was given).

## Before you start

Read, in order:
1. `.claude/context/audio-pipeline/integration-checklist.md` — the actual checklist items (read it fresh each run; do not rely on a cached memory of it, it may have been updated).
2. `.claude/context/audio-pipeline/stage-specifications.md` — what each stage is supposed to do, so you can judge behavior, not just presence of code.
3. `.claude/context/audio-pipeline/test-scenarios.md` — the scenario list referenced by the checklist's "scenario coverage" item.
4. The current code in `backend/app/modules/audio/` and `backend/app/schemas/detector.py`.

## What to check, per item in integration-checklist.md

For each checklist item, determine PASS / FAIL / UNVERIFIABLE (not just assume):

- **Exact schema** — actually inspect the return statements/paths in the code (or run it, if feasible) to confirm the 4-key `DetectorResult` shape is honored in every branch, not just the happy path.
- **Error semantics** — find every place the module can fail internally and confirm `error` is populated with `score` set to `null` in that case.
- **Graceful degradation** — check for explicit handling of corrupt/empty input; if none exists, this is a FAIL, not an assumption of "probably fine."
- **Hard gate behavior** (Stages 1 & 2) — confirm a failed gate sets `passed = False` and stops the pipeline (skips later stages) rather than raising or continuing silently.
- **Scenario coverage** — determine whether the module has actually been exercised against at least 3 of the 10 scenarios in `test-scenarios.md`, with real recorded output. If there's no evidence of this (no test file, no logged results), mark it FAIL/UNVERIFIABLE rather than giving benefit of the doubt — ask the user if scenario runs happened outside this repo.

If `$ARGUMENTS` names a specific stage, still report on all 5 checklist items but scope the "scenario coverage" and "hard gate" checks to what's relevant for that stage.

## Output format

A table: checklist item → PASS / FAIL / UNVERIFIABLE → one-line evidence or reason. Then a clear verdict line: **"READY FOR HANDOFF"** only if every item is PASS, otherwise **"NOT READY"** with the specific blocking items listed. Do not fix issues automatically — report them and wait for direction, unless the user has already asked you to fix what this check finds.
