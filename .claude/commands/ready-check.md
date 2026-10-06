---
description: Check whether a module change is really done - contract, error handling, must-pass behaviour, tests and scenario evidence.
argument-hint: "[optional: the module or change to focus on, defaults to everything changed]"
allowed-tools: Read, Grep, Glob, Bash
---

Decide whether the change is ready to build on. Do not rubber-stamp it.

Read the current code, `.claude/context/audio-pipeline/audio-checks.md` and `test-scenarios.md` fresh; judge behaviour, not just the presence of code.

For each item give PASS / FAIL / UNVERIFIABLE with one line of evidence:

1. **Exact schema:** every return path (not just the happy path) returns the 4-key `DetectorResult`.
2. **Error semantics:** every internal failure sets `error` and leaves `score` as `None`.
3. **Graceful degradation:** corrupt, empty or missing input returns a valid result and never raises.
4. **Must-pass behaviour:** a failed must-pass check sets `passed=False` and stops later checks; advisory checks never change `passed`.
5. **Tests:** `cd backend && python -m pytest tests -q -rs` passes with no unexplained skips; new behaviour has a test, including a negative test.
6. **Scenario evidence:** how many of the 10 audio scenarios (or the visual and anti-spoofing ones) have been run on real recordings with the result logged? None logged means UNVERIFIABLE, not PASS.
7. **Docs:** thresholds and behaviour in `audio-checks.md` / `CLAUDE.md` match the code, and any change to a must-pass check, threshold, fusion weight or the contract has a line in `decisions.md`.

End with **READY** only if every item is PASS; otherwise **NOT READY** with the blocking items. Do not fix anything unless asked.
