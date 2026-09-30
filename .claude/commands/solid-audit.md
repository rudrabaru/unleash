---
description: Audit the audio module for SOLID / separation-of-concerns violations (>40-line runners, direct I/O outside _io.py, lazy imports, contract gaps); report-only.
argument-hint: "[path, defaults to backend/app/modules/audio/]"
allowed-tools: Read, Grep, Glob
---

Systematically audits the audio pipeline module (`backend/app/modules/audio/`) for adherence to SOLID principles, separation of concerns, and clean architectural boundaries.

## Scope

- `backend/app/modules/audio/` — all `.py` files
- `backend/tests/` — related audio test files

---

## Audit Checklist

### 1. Single Responsibility Principle (SRP) Scan
- Check for functions with > 40 lines of code.
- Check if any function performs multiple mixed responsibilities (e.g., file I/O + model inference + schema construction).
- Verify that result dictionary construction and scoring arithmetic are isolated in dedicated helper functions.

### 2. Dependency Inversion / DRY Audio I/O Scan
- Verify that `soundfile` or `scipy.io.wavfile` or `librosa.load` are NOT called directly in stage files (`_speech_gate.py`, `_phrase_compliance.py`, `_voice_authenticity.py`).
- Confirm all stage modules consume WAV data via `_io.py` (`read_wav_numpy` / `read_wav_torch`).

### 3. Dependency Initialization Scan
- Check all heavy ML/audio dependencies (`silero_vad`, `faster_whisper`, `librosa`, `torch`, `soundfile`).
- Verify they are loaded or verified at module initialization with `try/except` and recorded error status.
- Ensure no lazy imports are hidden inside helper function bodies.

### 4. 4-Key Contract & Error Encapsulation (LSP / ISP)
- Verify every public entry point (`run_*` and `process_audio_pipeline`) returns `DetectorResult`.
- Ensure top-level `try/except` blocks capture all unexpected exceptions and return compliant `DetectorResult` instances with `score=None` and populated `error`/`reason`.
- Check that advisory stages (e.g., Stage 3) return `passed=True` even when internal execution errors occur.

---

## Report Format

```
SOLID ARCHITECTURE AUDIT — backend/app/modules/audio/
=====================================================
Run date: <date>

1. SRP COMPLIANCE:
   - File: <filename>
     Status: [PASS / WARN / FAIL]
     Notes: <details>

2. I/O MODULARITY (DRY/DIP):
   - Status: [PASS / WARN / FAIL]
   - Direct audio I/O calls outside _io.py: <none / list>

3. DEPENDENCY INITIALIZATION:
   - Status: [PASS / WARN / FAIL]
   - Module init handling: <summary>

4. 4-KEY CONTRACT & ERROR HANDLING:
   - Status: [PASS / WARN / FAIL]
   - Exception safety: <summary>

VERDICT: <Overall summary and list of recommended refactors if any>
```
