---
description: Reprocess already-recorded scenario audio across a sweep of candidate threshold values and report resulting TAR/FAR/FRR per value — Phase 4 tuning, report-only.
argument-hint: "<parameter to sweep, e.g. 'Stage 1 speech_duration'> <range, e.g. '1.5 to 2.5 step 0.25'>"
allowed-tools: Read, Grep, Glob, Bash
---

You are running the **threshold sensitivity sweep** named in the Unleash agentic development guide (Part 4, Automation #7). This turns Phase 4 threshold tuning from manual table-making into an automated sweep — but it is a **reporting tool**, not a tool that changes live thresholds itself.

Arguments: `$ARGUMENTS` — the parameter to sweep and the range/step. If unclear, ask rather than guessing which threshold or which range was meant.

## Before running

1. Read `.claude/context/audio-pipeline/eval-results.csv` (produced by `/scenario-runner`) — this sweep only reprocesses **already-recorded** audio, it does not go capture new recordings.
2. Read `.claude/context/audio-pipeline/stage-specifications.md` for the current live value of the parameter being swept (Stage 1 duration threshold currently 2.0s, Stage 2 digit-match tolerance currently 2-of-3, Stage 3 spectral threshold — confirm the current number rather than assuming these haven't already been tuned).
3. Read root `CLAUDE.md` Section F for the TAR/FAR/FRR targets this sweep is being judged against (TAR > 85%, FAR < 5%, FRR < 15%).

## What to do

1. For each candidate value in the requested range, recompute pass/fail for every recording already logged in `eval-results.csv` under that hypothetical threshold (re-running the actual matching/gating logic with the substituted value — not just eyeballing scores).
2. Compute TAR, FAR, and FRR at each candidate value.
3. Identify which value(s), if any, meet all three targets simultaneously, and note the tradeoff if none do (e.g. "2.25s gets FRR to 12% but pushes FAR to 6%").

## Output format

A table: candidate value → TAR → FAR → FRR → meets-all-targets (Y/N). Close with a plain-language recommendation, but **do not edit the live threshold constant in the audio module code or `stage-specifications.md` yourself** — this command's job ends at producing the evidence; the developer decides and asks separately for the code+doc change (which, per `integration-checklist.md`'s closing note, must update `stage-specifications.md` and, if it's a hard-gate threshold, root `CLAUDE.md` too, in the same commit).
