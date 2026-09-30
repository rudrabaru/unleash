# Dev 1 — Audio Pipeline Agentic Workspace

This folder is the "mission briefing" Claude Code reads specifically when working on the audio pipeline vertical (`backend/app/modules/audio/` and the mic-capture UI). It exists so this level of detail doesn't have to live in the shared root `CLAUDE.md` — read that file first for team-wide context, then this folder for the audio-specific deep spec.

**Read order when starting audio work:**
1. `/CLAUDE.md` (repo root) — team-wide context, the 4-key contract, ownership map, hard gates
2. `stage-specifications.md` — what each of the four stages does, inputs/outputs, thresholds
3. `known-tricky-spots.md` — implementation gotchas already identified; don't rediscover these
4. `integration-checklist.md` — what "done" means before handing a stage to Dev 3's orchestrator
5. `test-scenarios.md` — the scenarios every stage must be validated against
6. `automation-workflow.md` — the layered automation model (CI vs. slash commands vs. hooks vs. human approval), the phase-gate commit/push/PR workflow, and how to prompt Claude Code so the right slash command gets invoked reliably
7. `av-alignment-interface.md` — currently a blank placeholder; do not implement Stage 4 beyond a stub until this is filled in after the Day 19 design session with Dev 2

**Available slash commands:** the canonical list lives in `AGENTS.md` §3 (single source of truth — 12 commands). The audio-pipeline ones are `/schema-check`, `/stage-done`, `/stub-interface-check`, `/latency-benchmark`, `/graceful-failure-audit`, `/scenario-runner`, `/threshold-sweep`; plus the general `/session-worklog`, `/commit-message`, `/dead-code-audit`, `/solid-audit`, `/start-feature`. See `automation-workflow.md` for when to use each.

**Ownership:** This folder and everything under `backend/app/modules/audio/` belongs exclusively to Dev 1. Claude Code should not modify Dev 2's or Dev 3's module folders from here.

**Living documents:** When a threshold changes based on evaluation evidence (Phase 4), update `stage-specifications.md` and the root `CLAUDE.md` (if the change touches a hard gate) in the same commit. Stale instructions produce stale guidance.
