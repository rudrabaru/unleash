---
description: Re-score already-recorded evaluation results across candidate threshold values and report TAR/FAR/FRR per value; report only.
argument-hint: "<parameter> <range, e.g. 'speech duration 1.5 to 2.5 step 0.25'>"
allowed-tools: Read, Grep, Glob, Bash
---

This reports; it never changes a live threshold.

1. Read `backend/eval/results.csv` (made by `/scenario-runner`). It only reprocesses recordings that already exist. If the file does not exist or has too few rows, say so and stop: there is nothing to sweep yet.
2. Read the current value of the parameter from the code (`audio-checks.md` lists them: speech duration 2.0 s, phrase 4 of 5, similarity 0.8, per-word confidence 0.5) and the targets in `CLAUDE.md` (TAR above 85%, FAR below 5%, FRR below 15%).
3. For each candidate value recompute pass/fail for every recorded clip with the real matching or gating code, and compute TAR, FAR and FRR.
4. Output a table: value -> TAR -> FAR -> FRR -> meets all targets, then a plain-language recommendation with the trade-off. State the sample size next to every rate.

Changing a threshold is the owner's decision: it needs the code change, `audio-checks.md` and a line in `decisions.md` in one commit, asked for separately.
