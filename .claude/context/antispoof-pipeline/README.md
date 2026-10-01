# Dev 3 — Anti-Spoofing Pipeline Agentic Workspace

This folder is the "mission briefing" Claude Code reads specifically when working on the anti-spoofing vertical (`backend/app/modules/antispoof/`, fusion engine, orchestrator, and eval dashboard API). It exists so this level of detail doesn't have to live in the shared root `CLAUDE.md` — read that file first for team-wide context, then this folder for the antispoof-specific deep spec.

**Read order when starting antispoof work:**
1. `/CLAUDE.md` (repo root) — team-wide context, the 4-key contract, ownership map, hard gates, fusion weights, thresholds
2. `stage-specifications.md` — what each detector does (deepfake, replay), algorithms, thresholds
3. `known-tricky-spots.md` — implementation gotchas already identified; don't rediscover these
4. `integration-checklist.md` — what "done" means before handoff to orchestrator
5. `test-scenarios.md` — the scenarios every detector must be validated against
6. `automation-workflow.md` — the layered automation model and when to use each slash command
7. `fusion-engine.md` — hard gates, joint veto logic, weighted scoring, null-signal redistribution, threshold bands

**Current Implementation Status:**
- ✓ Deepfake detector (self-trained Xception, CPU-only, real model checkpoint present)
- ✓ Replay detector (FFT moiré 55% / temporal noise 30% / brightness 15%, pass ≥0.60)
- ✓ Fusion engine (hard gates, joint veto, weighted score, null-signal redistribution, thresholds: VERIFIED ≥0.80, SUSPICIOUS 0.55–0.79, FAILED <0.55)
- ✓ Orchestrator (frame extraction once, all detectors isolated via `_safe_call`, temp cleanup)
- ✓ SQLite database (sessions, signal_scores, error_log tables, real persistence, no in-memory dict)
- ✓ Sessions API (HMAC sign/verify, 120s expiry, single-use via status gate, temp cleanup guaranteed)
- ✓ Eval API (GET /eval/sessions for dashboard, real database backend)
- ✓ All modules return strict 4-key DetectorResult schema
- ✓ Schema compliance verified: 5/5 tests passed, all edge cases handled gracefully

**Module Responsibility Map (Runtime):**
- `_config.py` — Configuration dataclass for deepfake detector (model path, device, etc.)
- `_deepfake.py` — Xception-based deepfake classification (frame sampling, preprocessing, scoring)
- `_replay.py` — Replay attack detection via FFT moiré + temporal noise + brightness heuristics
- `_face_crop.py` — Primary face detection via Haar cascade (supports optional cropping)
- `__init__.py` — Both detector entrypoints + exception wrapping via `_safe_call`

**Module Responsibility Map (Backend Core & Integration):**
- `backend/app/orchestrator.py` — Session submission orchestration (extract frames once, call all 5 detectors, fusion, persist, cleanup)
- `backend/app/fusion.py` — Hard gates, joint veto, weighted scoring, null redistribution, thresholds
- `backend/app/db.py` — SQLite schema + CRUD for sessions, signals, errors
- `backend/app/api/v1/endpoints/sessions.py` — Session creation + submit (calls orchestrator)
- `backend/app/api/v1/endpoints/eval.py` — Evaluation dashboard API (read-only queries)

**Training Module (Development-Only):**
- `training/train_xception.py` — Standalone training script for Xception deepfake classifier
- NOT imported by runtime; managed separately as dev-only tooling

**Available slash commands:** `/schema-check`, `/stage-done`, `/latency-benchmark`, `/graceful-failure-audit`, `/scenario-runner`, `/threshold-sweep`, `/dead-code-audit`, `/solid-audit`, `/commit-message`.

**Ownership:** This folder, `backend/app/modules/antispoof/`, and the backend-core modules (`orchestrator.py`, `fusion.py`, `db.py`) belong to Dev 3. The API endpoints are split-owned (sessions creation is Dev 2, submit/orchestration is Dev 3). Claude Code should not modify Dev 1's or Dev 2's module folders from here.

**Known Open Issue (Tracked):**
- `fusion.py:82-88` — Missing fallback for `av_alignment_score` from audio details (voice_authenticity_score fallback exists, but av_alignment was silently dropped). RESOLVED: Added av_alignment fallback from audio_pipeline.details mirroring voice_authenticity pattern.

**Living documents:** When a threshold changes based on evaluation evidence (Phase 4), update the relevant specs in this folder and the root `CLAUDE.md` (if the change touches fusion weights or hard gates) in the same commit.

**Next Milestone:** Phase 4 evaluation — record 8–10 samples for each of 8 documented antispoof scenarios, validate FAR/APCER breakdown per attack species, tune replay + deepfake thresholds + fusion weights with evidence.
