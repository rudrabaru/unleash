---
description: Stress-test the audio pipeline's failure surface per-stage (corrupt/empty/wrong-sample-rate/non-audio/noise-only input) before any stage is called "implemented."
argument-hint: "[optional: which stage to audit, e.g. 'Stage 2', defaults to all stages]"
allowed-tools: Read, Grep, Glob, Bash
---

You are running the **graceful failure audit** named in the Unleash agentic development guide (Part 4, Automation #5). This is deliberately distinct from `/schema-check`: that command verifies the 4-key *shape* via a handful of malformed inputs at the top-level entrypoint. This command stress-tests the **audio-domain failure surface specifically**, per-stage, using the failure modes actually named in `.claude/context/audio-pipeline/known-tricky-spots.md` and `stage-specifications.md`.

Scope: `$ARGUMENTS` (default: audit every stage that currently has real, non-stub code).

## Failure inputs to construct/use, per stage

- An empty file (0 bytes)
- A non-audio file with an audio-like extension (e.g. a text file renamed `.wav` or `.webm`)
- A corrupt/truncated audio file (a valid file with the last N bytes chopped off)
- Wrong-sample-rate audio (e.g. 8kHz or 44.1kHz stereo) — per `known-tricky-spots.md` #5, the module must **always force-resample to 16kHz mono regardless of input**, so this specifically tests that assumption isn't silently violated
- Noise-only / silence audio (relevant to Stage 1's speech gate specifically)
- A missing/nonexistent file path

## What to do

1. Read the current code for each in-scope stage (not just the top-level `process_audio_pipeline` entrypoint — call into the actual stage function where feasible, since a bug caught only at the top level might be masked by an outer try/except).
2. Run each failure input against each in-scope stage. Confirm the ffmpeg subprocess call (if reached) fails gracefully rather than crashing the process, and that any exception is caught and translated into a valid schema result — never a raised, uncaught exception.
3. For any stage that isn't real code yet (still returning a stub value), say so explicitly rather than reporting a false PASS.

## Output format

A table: stage × failure-input → PASS (valid schema returned, `error` populated, `score` null) / FAIL (crashed, or returned a numeric score alongside an error, or silently gave a "normal" result) / N/A (stage not real yet). Do not add a broad `try/except: return default` as an unrequested fix for any FAIL — report which specific input breaks which specific stage and wait for direction, since masking the failure could hide a real bug rather than fix it.
