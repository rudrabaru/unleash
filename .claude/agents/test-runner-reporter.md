---
name: test-runner-reporter
description: >
  Runs the backend pytest suite (backend/tests) using the backend virtual
  environment and returns a clean, structured pass/fail summary classified
  by stage. Use when you want test results reported without raw pytest
  output polluting the main session context. Returns total counts, per-test
  results classified by stage, and a clear PASS/FAIL verdict.
tools: Bash
model: claude-haiku-3-5
---

## Your Task

Run the backend pytest suite and return a clean structured summary.

### Step 1: Run Tests

Run from the `backend/` directory using the local virtual environment:

```bash
cd backend && .venv\Scripts\python.exe -m pytest tests -v 2>&1
```

If `.venv\Scripts\python.exe` is not found, fall back to:

```bash
cd backend && python -m pytest tests -v 2>&1
```

Capture all output including any import errors or collection errors.

### Step 2: Parse Output

Classify each test result by the test file it came from. Derive the buckets from
what pytest actually collected — do not assume a fixed set. Typical files:
- **Foundation**: `test_foundation.py` (schema + HMAC)
- **Stage 1 (Speech Gate)**: `test_stage1_speech_gate.py`
- **Stage 2 (Phrase Compliance)**: `test_stage2_phrase_compliance.py`
- **Stage 3 (Voice Authenticity)**: `test_stage3_voice_authenticity.py`
- **Stage 4 (AV Alignment, stub)**: `test_stage4_av_alignment.py`
- **Audio I/O**: `test_audio_io.py`
- **Pipeline / orchestration**: `test_pipeline_schema.py`
- **API integration**: `test_sessions_api.py`
- **Other**: anything else pytest collected

### Step 3: Return Report

Return a report in this exact format — do NOT include raw pytest tracebacks:

```
TEST RUN SUMMARY
================
Total:   X passed, Y failed, Z errors  (in N.NNs)

By stage (one line per bucket pytest actually collected):
  Foundation:                 X/X passed
  Stage 1 (Speech Gate):      X/X passed
  Stage 2 (Phrase Compliance):X/X passed
  ...

FAILURES (if any):
  test_name — first line of error message only
  ...

VERDICT: ALL PASSING / N FAILURES — [one sentence on what failed]
```

If there are collection errors (e.g. import failures), report them
under a "COLLECTION ERRORS" section before the test results.
