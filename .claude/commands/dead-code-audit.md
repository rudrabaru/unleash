---
description: Find dead functions, unused imports and requirement drift across the backend; report only until the owner approves deletions.
argument-hint: "[optional: a folder to limit the audit to]"
allowed-tools: Read, Grep, Glob, Bash, Edit
---

Find code that nothing uses. Never delete anything without approval.

## Scope

`backend/app/`, `backend/tools/`, `backend/tests/`, `backend/requirements.txt`, `backend/requirements-dev.txt` (or `$ARGUMENTS`).

## Steps

1. **Unused imports and names:** run `ruff check --isolated --select F backend/app backend/tests backend/tools` (install ruff if missing) and read the findings.
2. **Unreferenced symbols:** list every `def`, `class` and module-level constant with grep. For each, search the whole repo (app, tests, tools). Classify it as live (reachable from `app.main`, `orchestrator.analyze_media` or a tool), test-only, or unreferenced.
3. **Requirement drift:** for each package in the requirements files, name the files that import it (mind pip name vs import name, e.g. `opencv-contrib-python` is `cv2`). Flag packages declared but never imported *and* not needed by another package, and imports with no requirement.
4. **Leftovers:** stale comments naming files that no longer exist, tests asserting nothing, fixtures no test uses.

## Report

```
DEAD CODE AUDIT
Run date / trigger:
UNREFERENCED SYMBOLS:   file:line symbol - evidence
TEST-ONLY SYMBOLS:      file:line symbol - tests that use it
UNUSED IMPORTS:         file:line
REQUIREMENT DRIFT:      declared-not-imported / imported-not-declared
CANDIDATE DELETIONS (awaiting approval): [ ] ...
```

After the owner approves specific items: delete them, run `cd backend && python -m pytest tests -q`, and revert only the deletion that broke a test.
