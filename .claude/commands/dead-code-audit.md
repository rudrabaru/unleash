---
description: Find dead functions, unused imports, and requirements-audio.txt dependency drift in the audio module; report-only until the user approves deletions.
argument-hint: "[trigger note — post-stage, pre-PR, manual]"
allowed-tools: Read, Grep, Glob, Bash, Edit
---

Systematically identifies dead, stale, and dependency-drift issues in the audio pipeline module. Never deletes anything automatically — produces a structured report and waits for user approval.

## Scope

- `backend/app/modules/audio/` — all `.py` files
- `backend/requirements-audio.txt` — declared packages
- `backend/tests/` — to verify nothing classified as "dead" is actually used by tests

---

## Step 1 — Map the Call Graph

Read `backend/app/modules/audio/__init__.py` in full. Identify:
- The single public entrypoint: `process_audio_pipeline()`
- Every internal function/class it calls directly
- Every internal function/class those calls invoke (one level deep is sufficient)

Build a flat list of **reachable symbols** in `backend/app/modules/audio/`.

---

## Step 2 — Scan All Symbols Defined in the Module

Use Grep to list every function and class defined across all `.py` files in `backend/app/modules/audio/`:

```
grep -n "^def \|^class \|^    def " backend/app/modules/audio/*.py
```

Cross-reference against the reachable symbol list from Step 1. Flag any symbol that is:
- Defined but never in the reachable set
- Not called by any test in `backend/tests/`
- Not a documented stub (marked with `# Stage N stub`)

---

## Step 3 — Scan All Imports

For each `.py` file in `backend/app/modules/audio/`, read the import block and check:
- Is every imported name (module, function, class) actually used in that file?
- Flag any import that exists only in the import block and nowhere else in the file

```
grep -n "^import \|^from " backend/app/modules/audio/*.py
```

---

## Step 4 — Dependency Drift Check

Read `backend/requirements-audio.txt`. For each package listed:
- Grep for any `import <package>` or `from <package>` in `backend/app/modules/audio/` AND `backend/tests/`
- Flag any package that is declared in requirements but imported by zero files

Also check the reverse: are there any `import` statements in the audio module that reference packages NOT listed in `requirements-audio.txt`? These are undeclared dependencies and are also flagged.

---

## Step 5 — Report

Output a structured report in this format. Never delete, rename, or modify anything:

```
DEAD CODE AUDIT — backend/app/modules/audio/
============================================
Run date: <date>
Trigger: <why this was run — post-stage, pre-PR, manual, etc.>

UNREACHABLE FUNCTIONS/CLASSES:
  File: _extraction.py
    Line 88: def _old_helper() — not called by any reachable path or test
  ... or "none"

UNUSED IMPORTS:
  File: _speech_gate.py
    Line 3: import os — imported but never used
  ... or "none"

DEPENDENCY DRIFT:
  Declared in requirements-audio.txt but never imported:
    - torchaudio (declared, zero usages found)
  ... or "none"

  Imported but not declared in requirements-audio.txt:
    - webrtcvad (imported in _speech_gate.py, not in requirements-audio.txt)
  ... or "none"

CANDIDATE DELETIONS (awaiting user approval):
  [ ] backend/app/modules/audio/_extraction.py:88 — def _old_helper()
  [ ] backend/app/modules/audio/_speech_gate.py:3 — import os

VERDICT: N issues found. Awaiting user approval before any deletion.
```

---

## Step 6 — After User Approval

Only after the user explicitly approves specific items:
1. Apply the approved deletions
2. Run `python -m py_compile` on any modified file
3. Run `cd backend && .venv\Scripts\python.exe -m pytest tests -v`
4. Report pass/fail. If tests fail, identify which deletion caused it and revert only that item.
