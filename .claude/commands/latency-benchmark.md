---
description: Time each analysis step and the whole request against the latency budgets; report only.
argument-hint: "[optional: a clip path, defaults to the manifest clips]"
allowed-tools: Read, Grep, Glob, Bash
---

Measure, do not guess.

## Budgets (from `CLAUDE.md`)

Whole analysis (submission to result) under 20 s; speech plus phrase checks under 10 s.

## What to do

1. Check the known bug class first: models (Whisper, silero-vad, MediaPipe landmarker, Xception) must be created at import or once, not inside a request path.
2. Run `cd backend && .venv\Scripts\python.exe tools/measure_clips.py` (or `orchestrator.analyze_media` on one clip, whose `timings` dict has the time of every step) twice: the first run is cold, the second warm. Report the warm numbers per step: frames, landmarks, audio, visual_liveness, visual_challenge, deepfake, replay, fusion, total.
3. Report peak memory if you can measure it.

## Report

A table: step -> seconds -> note, with the total against the 20 s budget. If the budget fails, say whether the cause is a per-request model load, genuine inference cost (the deepfake model dominates), or unclear. Do not change models, add caching or adjust timeouts to improve the numbers; report and wait.
