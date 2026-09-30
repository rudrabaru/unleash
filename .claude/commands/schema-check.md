---
description: Verify the audio module's output exactly matches the 4-key DetectorResult schema, including malformed-input edge cases.
argument-hint: "[path to audio module, defaults to backend/app/modules/audio/]"
allowed-tools: Read, Grep, Glob, Bash
---

You are running the **audio module schema compliance check** described in the Unleash agentic development guide (Part 4, Automation #1) and the Stage-Level Integration Checklist (`.claude/context/audio-pipeline/integration-checklist.md`, first two items).

Target module: `$ARGUMENTS` (default to `backend/app/modules/audio/` if no argument was given).

## What "compliant" means

Read `backend/app/schemas/detector.py` for the authoritative `DetectorResult` definition, and the root `CLAUDE.md` Section B for the contract in prose. Every call into the audio module's public entrypoint (currently `process_audio_pipeline` in `backend/app/modules/audio/__init__.py` — confirm the actual current signature by reading the file, don't assume it hasn't changed) must return an object that satisfies **all** of the following:

1. `score` is either `None`, or a `float` in the closed range `[0.0, 1.0]`. Never a string, never an int outside that range, never missing.
2. `passed` is a real Python `bool` (`True`/`False`) — not a string like `"true"`, not `1`/`0`, not `None`.
3. `reason` is a non-empty string.
4. `error` is `None` on success. When `error` is a non-`None` string, `score` **must** be `None` in the same result — a numeric score alongside a populated error is a contract violation.
5. The function **never raises an uncaught exception**, regardless of input — every failure path must still return a valid `DetectorResult`-shaped object with `error` populated instead of propagating.

## What to do

1. Read the audio module's current code to find its entrypoint(s) and understand what inputs they expect.
2. Construct and run a small set of test invocations covering:
   - A normal/valid input (whatever the module currently expects — a real or synthetic audio/media file, if one exists in the repo or test fixtures; otherwise construct a minimal valid one).
   - An empty file.
   - A corrupt / non-audio file (e.g. a text file with a `.webm` or `.wav` extension).
   - A missing/nonexistent file path.
   - Any other malformed input the current function signature makes plausible (e.g. an empty or garbage `challenge_phrase`).
3. For each case, capture the actual returned value (or exception, if one leaks) and check it against the 5 rules above.
4. If running the module requires a Python environment that isn't set up, say so explicitly rather than skipping the check — do not silently mark unverified cases as "passed."

## Output format

Report a compact table: test case → actual result summary → PASS/FAIL against the 5 rules, with the specific rule violated for any FAIL. End with one line: total pass/fail count and whether the module is schema-compliant overall. If anything is a FAIL, do not fix it automatically — report it and wait for confirmation before editing code, unless the user has already asked you to fix issues found by this check.
