# Dev 2 — Visual Pipeline Agentic Workspace

This folder is the "mission briefing" Claude Code reads specifically when working on the visual pipeline vertical (`backend/app/modules/visual/` and the camera-capture UI). It exists so this level of detail doesn't have to live in the shared root `CLAUDE.md` — read that file first for team-wide context, then this folder for the visual-specific deep spec.

**Read order when starting visual work:**
1. `/CLAUDE.md` (repo root) — team-wide context, the 4-key contract, ownership map, hard gates
2. `stage-specifications.md` — what each module does (liveness detection, challenge compliance), inputs/outputs, thresholds
3. `known-tricky-spots.md` — implementation gotchas already identified; don't rediscover these
4. `integration-checklist.md` — what "done" means before handing the module to Dev 3's orchestrator
5. `test-scenarios.md` — the scenarios every module must be validated against
6. `automation-workflow.md` — the layered automation model and when to use each slash command
7. `av-alignment-interface.md` — finalized interface for lip-openness series output to Dev 1's Stage 4

**Current Implementation Status:**
- ✓ Liveness detection (EAR-based blink, micro-movement, consistency scoring)
- ✓ Challenge compliance (head pose via rotation matrices, yaw/pitch thresholds, 5 challenge types including BLINK_TWICE)
- ✓ Lip openness series extraction (face-height-normalized, per-frame, with fps annotation for Stage 4 alignment)
- ✓ All modules return strict 4-key DetectorResult schema
- ✓ Schema compliance verified: 5/5 tests passed, all edge cases handled gracefully

**Module Responsibility Map:**
- `_landmarks.py` — MediaPipe face landmark extraction (468 landmarks) + landmarker lifecycle
- `_liveness.py` — EAR calculation, blink signal, micro-movement detection, liveness scoring
- `_pose.py` — 3D rotation matrix → Euler angles (yaw/pitch/roll), baseline + displacement calculation, challenge evaluation
- `_lip_series.py` — Per-frame lip openness ratio extraction + fps annotation for Stage 4 AV alignment
- `__init__.py` — Pipeline orchestration, both detector entrypoints (liveness + challenge compliance)

**Available slash commands:** `/schema-check`, `/stage-done`, `/latency-benchmark`, `/graceful-failure-audit`, `/scenario-runner`, `/threshold-sweep`, `/dead-code-audit`, `/solid-audit`, `/commit-message`.

**Ownership:** This folder and everything under `backend/app/modules/visual/` belongs exclusively to Dev 2. Claude Code should not modify Dev 1's or Dev 3's module folders from here.

**Living documents:** When a threshold changes based on evaluation evidence (Phase 4), update the relevant specs in this folder and the root `CLAUDE.md` (if the change touches a hard gate) in the same commit.

**Next Milestone:** Phase 4 evaluation — record 8–10 samples for each of 9 documented scenarios, validate TAR/FAR/FRR metrics, tune thresholds with evidence.
