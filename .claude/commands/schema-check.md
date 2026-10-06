---
description: Verify every detector's output against the 4-key DetectorResult contract, including malformed input, and that callers use the entry points correctly.
argument-hint: "[optional: one detector, e.g. audio, visual, deepfake, replay]"
allowed-tools: Read, Grep, Glob, Bash
---

Check the contract in `backend/app/schemas/detector.py` against what the detectors really return. Read the file first; do not assume.

## Rules a result must satisfy

1. `score` is `None` or a float in [0, 1].
2. `passed` is a real `bool`.
3. `reason` is a non-empty string.
4. `error` is `None` or a string, and **when `error` is set, `score` must be `None`**. The reverse is not required: a must-pass check that fails (silence, wrong phrase) legitimately returns `score=None, error=None, passed=False`, and an advisory check with no data returns `score=None, error=None`.
5. The function never raises, whatever the input.

## What to run

Detectors: `process_audio_pipeline`, `detect_visual_liveness`, `verify_challenge_compliance`, `detect_deepfake`, `detect_replay_attack` (all plain blocking functions). For each, call it with: a valid input, an empty or missing input, a corrupt file or frames, and (audio) a challenge phrase that is not 5 words. Use the clips in `backend/tests/fixtures` and the generated clips in `tests/conftest.py`. Use the backend virtual environment (`backend/.venv`); if it is missing, say so instead of skipping.

## Interface check

Find every call site of each entry point (`backend/app/orchestrator.py`, tools, tests) and confirm the argument names, order and types match the definition, and that callers only read fields that exist (`score`, `passed`, `reason`, `error`, `details`) and the `details` keys fusion reads (`voice_authenticity_score`, `av_alignment_score`). Report which side is stale; do not edit either side.

## Report

A table: detector x case -> PASS/FAIL with the rule violated, and one line with the total. Do not fix anything unless asked.
