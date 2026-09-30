# Rule: SOLID Audio Pipeline Architecture & Modularity

## Purpose
Enforce strict adherence to SOLID design principles and separation of concerns across the audio pipeline (`backend/app/modules/audio/`) for all current and future implementations.

---

## 1. Module Responsibility Map

Each file within `backend/app/modules/audio/` has exactly **ONE** designated responsibility:

| File | Single Responsibility | Boundaries / Forbidden Logic |
|---|---|---|
| `_io.py` | Audio file loading, decoding, format normalization (16kHz mono PCM) | No model inference, no heuristics, no scoring. |
| `_extraction.py` | Container probing, FFmpeg track extraction, completeness checks | No speech analysis or classification. |
| `_speech_gate.py` | Stage 1: Voice Activity Detection (VAD) & speech duration gating | No STT, no spectral analysis, no audio decoding logic (uses `_io.py`). |
| `_phrase_compliance.py` | Stage 2: Automatic Speech Recognition (ASR) & challenge matching | No VAD gating, no spectral analysis. |
| `_voice_authenticity.py` | Stage 3: Spectral heuristic feature extraction & authenticity scoring | No file container decoding (uses `_io.py`), advisory only (never hard-fails). |
| `_av_alignment.py` | Stage 4: Audio-visual temporal correlation & cross-modal alignment | Audio/video cross-modal matching only. |
| `__init__.py` | Pipeline orchestration, sequential stage dispatch, result merging | No inline feature extraction, no deep heuristic logic. |

---

## 2. SOLID Principles Applied to Audio Pipeline

### S — Single Responsibility Principle (SRP)
- **Rule**: Functions must perform a single logical task. Keep stage runner functions under 40 lines by delegating sub-tasks.
- **DO**: Extract helpers for:
  - Feature calculations (e.g., `compute_noise_floor_score`, `compute_spectral_flux_score`)
  - Gate evaluation decisions (e.g., `_evaluate_speech_gate`)
  - Score derivations (e.g., `_compute_composite_score`, `_compute_pipeline_score`)
  - Result dict formatting (e.g., `_build_advisory_error_result`, `_build_advisory_success_result`)
- **DON'T**: Combine file I/O, VAD slicing, spectral math, and JSON schema formatting in a single monolithic function.

### O — Open / Closed Principle (OCP)
- **Rule**: Pipeline stages must be extensible without modifying existing stage implementations.
- **DO**: Define independent stage interfaces where adding a new stage (e.g., Stage 4) or a new heuristic only requires registering the new runner or adding a weighted component, without rewriting preceding stages.
- **DON'T**: Hardcode cross-stage dependencies where Stage 2 depends on Stage 3 internals.

### L — Liskov Substitution Principle (LSP)
- **Rule**: Every stage runner (`run_*`) must return a valid `DetectorResult` compliant with the **4-Key Contract** (`score`, `passed`, `reason`, `error`, `details`).
- **DO**: Ensure every detector can be called and processed uniformly by the orchestrator.
- **DON'T**: Return raw primitives, custom tuples, or raise unhandled exceptions from stage runners.

### I — Interface Segregation Principle (ISP)
- **Rule**: Stage functions must only take the inputs they actually require to execute.
- **DO**: Pass strictly `wav_path: Path | str` and optional pre-computed segments (`speech_segments`) rather than massive global state objects or raw request contexts.
- **DON'T**: Force stages to receive unneeded HTTP request objects or unrelated detector configurations.

### D — Dependency Inversion Principle (DIP)
- **Rule**: High-level stage modules must depend on shared utility abstractions, not duplicated low-level file I/O.
- **DO**: Import WAV reading and tensor/numpy conversion functions from `_io.py`.
- **DO**: Handle heavy ML model loading at module initialization with graceful fallbacks and clear error flags (e.g., `_MODEL_LOAD_ERROR`).
- **DON'T**: Call `soundfile.read` or `librosa.load` independently across multiple stage files with slightly differing logic.

---

## 3. Developer & Agent Checklist (Mandatory Gate)

Before finalizing any stage implementation, refactor, or feature addition in `backend/app/modules/audio/`:

1. [ ] **Single Responsibility**: Does each function in your change have only one reason to change?
2. [ ] **No Duplicate I/O**: Are all audio loading/decoding operations using `_io.py`?
3. [ ] **Module-Level Imports**: Are all heavy libraries (`librosa`, `faster-whisper`, `silero-vad`) initialized at module level with graceful fallback logging?
4. [ ] **4-Key Contract**: Does the stage runner return a valid `DetectorResult` and catch all internal exceptions?
5. [ ] **Advisory vs. Hard Gate**: If the stage is advisory (e.g., Stage 3), does it return `passed=True` with `score=None` and error details on failure?
6. [ ] **Tests Pass**: Does `pytest tests -v` run with 100% pass rate?
