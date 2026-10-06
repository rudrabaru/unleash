---
description: Stress-test each detector with corrupt, empty, wrong-format and non-speech/no-face input; report only.
argument-hint: "[optional: one detector, defaults to all]"
allowed-tools: Read, Grep, Glob, Bash
---

Find inputs that crash a detector or make it return something misleading. This is separate from `/schema-check`: that checks the result shape, this hunts for failure modes specific to audio and video.

## Inputs

- Empty file (0 bytes); a text file named `.webm`; a valid file cut off after a few KB; a missing path.
- Audio: wrong sample rate or stereo (the extraction must always force 16 kHz mono), silence, a tone, noise only, an audio-only file where video is expected.
- Video: a video-only file where audio is expected, a clip with no face, a very small or very large frame size, a clip shorter than 1 s.
- Call the real detector functions directly as well as the top-level `orchestrator.analyze_media`, so an outer `try/except` cannot hide a bug.

## Report

A table: detector x input -> PASS (valid result, `error` set, `score` `None`, no hang) / FAIL (raised, hung, or a numeric score together with an error, or a normal-looking result for garbage input). Mark detectors that cannot run in this environment as such, not as PASS. Do not add a blanket `try/except` as a fix; report which input breaks which detector and wait.
