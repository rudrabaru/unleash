---
description: Check module structure - function length, duplicated I/O, import-time model loading and contract handling; report only.
argument-hint: "[optional: a module folder, defaults to backend/app/modules/]"
allowed-tools: Read, Grep, Glob
---

Check that each module keeps one responsibility per file and that detectors honour the result contract. Report only.

## Checks

1. **Function length:** list functions with more than about 40 lines of code (not counting the docstring); say what mixed responsibilities they hold (I/O, inference, scoring arithmetic, result building).
2. **One place for each job:** audio decoding only in `audio/_io.py`; ffmpeg/ffprobe only in `audio/_extraction.py`; video decoding only in `media/frames.py`; one shared constant for the audio format (`audio/_constants.py`) and one `sample_indices` (`media/sampling.py`). Flag duplicates.
3. **Models load once at import** (silero-vad, faster-whisper, librosa warm-up, the MediaPipe landmarker is created once and the Xception checkpoint once) and are never created inside a request path. Flag heavy imports hidden inside function bodies.
4. **Contract:** every public detector entry point returns `DetectorResult`, catches all exceptions and returns `score=None` with `error` set (never a score together with an error). Advisory checks return `passed=True` even when they error.
5. **Blocking work is not `async`:** no `async def` around CPU-bound or blocking code; analysis runs in worker threads under `orchestrator._ANALYSIS_LOCK`.

## Report

For each module: PASS / WARN / FAIL with file:line evidence, then a short list of recommended refactors.
