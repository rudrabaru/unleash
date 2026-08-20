---
description: Time each audio stage and the combined Stage 1-3 path against the project's latency budgets, and check for the known per-request-model-load bug class.
argument-hint: "[optional: which stage(s) to benchmark, defaults to the full pipeline]"
allowed-tools: Read, Grep, Glob, Bash
---

You are running the **model latency benchmark** named in the Unleash agentic development guide (Part 4, Automation #3). On shared CPU, latency problems discovered late in the project are expensive — this exists to catch them per-stage, early.

Scope: `$ARGUMENTS` (default: the full audio pipeline).

## Budgets to check against

Read root `CLAUDE.md` Section F and `.claude/context/audio-pipeline/stage-specifications.md` for the authoritative numbers before assuming these are still current:
- Stage 1 (VAD): ~0.5s
- Stage 2 (STT): ~4–6s
- Stage 3 (spectral): ~1s
- **Stages 1–3 combined: < 10 seconds**
- Full pipeline (incl. Stage 4 once real): end-to-end analysis < 20 seconds

## What to do

1. Read the current audio module code to find the actual stage functions and the top-level entrypoint.
2. **Before timing anything, check for the known bug class first** (see `.claude/context/audio-pipeline/known-tricky-spots.md` items #1 and #4): is the faster-whisper model instantiated inside the request-handling path, or at module/process import time? If it's loaded per-call, flag this immediately as the likely root cause of any latency failure — fix-worthiness matters more than the raw number in that case.
3. Run a real timing pass: wall-clock each stage individually (`time.perf_counter()` around the actual call, not an estimate) against a real or synthetic audio sample, then time the combined Stage 1–3 (and full 1–4 if Stage 4 is no longer a stub) path.
4. If no test audio fixture exists to time against, say so explicitly and either construct a minimal synthetic WAV for timing purposes or ask before fabricating one that might not represent real speech characteristics.

## Output format

A table: stage → measured time → budget → PASS/FAIL, plus a combined-path row. If a stage fails, state explicitly whether the likely cause is (a) the per-request model-load bug, (b) genuine inference cost, or (c) unclear — and what evidence supports that read. Do not change model choice, add caching, or adjust timeouts to make numbers look better — report and wait for direction.
