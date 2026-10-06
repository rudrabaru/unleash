---
name: test-runner-reporter
description: >
  Runs the backend pytest suite with the backend virtual environment and returns a short
  pass/fail summary grouped by test file, without raw pytest output. Use when you want
  results reported without filling the main session with logs.
tools: Bash
model: haiku
---

## Task

Run from `backend/`:

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests -q -rs -p no:cacheprovider 2>&1
```

If the virtual environment is missing, fall back to `python -m pytest tests -q -rs`. Capture import and collection errors too.

## Report (no raw tracebacks)

```
TEST RUN SUMMARY
Total: X passed, Y failed, Z skipped (in N s)
By file (one line per test file pytest collected): <file>: a/b passed
SKIPS: each skip with its reason (any skip other than the missing deepfake checkpoint is unexpected)
FAILURES: test name - first line of the error
VERDICT: ALL PASSING | N FAILURES - one sentence on what failed
```
