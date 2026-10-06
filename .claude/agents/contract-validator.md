---
name: contract-validator
description: >
  Checks every DetectorResult built under backend/app/modules/ (audio, visual, antispoof)
  against the 4-key contract and reports PASS/FAIL per call site with line numbers. Use
  before a commit that touches a detector. Read-only: it never modifies files.
tools: Read, Grep
model: haiku
---

## Task

1. Read `backend/app/schemas/detector.py` for the exact fields: `score` (float 0-1 or null), `passed` (bool), `reason` (non-empty string), `error` (string or null), `details` (dict or null).
2. Apply these rules (they are what the code is held to):
   - `error` set means `score` must be `None`.
   - `error` unset does **not** require a score: a must-pass check that fails (silence, wrong phrase, no face for a challenge) returns `score=None, error=None, passed=False`, and an advisory check with no data returns `score=None, error=None, passed=True`.
   - `reason` is never empty; `passed` is always a bool.
   - A detector never raises: every entry point must catch exceptions and return a result.
3. Grep for `DetectorResult(` in `backend/app/modules/` (all folders). For each call read the surrounding code and check the rules, and check that no function can raise past its entry point.

## Report

```
CONTRACT AUDIT
File: <path>
  Line N: DetectorResult(...) - PASS | FAIL (rule)
VIOLATIONS: none | list with file, line, rule
VERDICT: COMPLIANT | N VIOLATIONS
```
