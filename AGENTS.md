# Unleash workspace rules (Antigravity IDE and Claude Code)

`CLAUDE.md` is the source of truth; read it first. This file only points to it.

- **Working mode:** solo (one owner). Changes to must-pass checks, thresholds, fusion weights, the detector contract or the upload design need the owner's explicit approval and a line in `.claude/context/decisions.md`.
- **Rules:** every file in [`.agents/rules/`](.agents/rules/) applies: ask before assuming, no hardcoded stub values, the detector contract, repo hygiene, commit messages.
- **Commands** (read `.claude/commands/<name>.md` and follow it): `/commit-message`, `/dead-code-audit`, `/solid-audit`, `/schema-check`, `/ready-check`, `/graceful-failure-audit`, `/latency-benchmark`, `/scenario-runner`, `/threshold-sweep`.
- **Subagents** (`.claude/agents/`): `contract-validator`, `test-runner-reporter`.
- **Hooks** (Claude Code only, `.claude/hooks/`): a confirmation prompt before editing `backend/app/schemas/detector.py`, and a syntax check after every Python edit.
- **Context:** [`.claude/context/audio-pipeline/`](.claude/context/audio-pipeline/) (audio checks, lip-series interface, gotchas, scenarios), [`.claude/context/decisions.md`](.claude/context/decisions.md), [`ROADMAP.md`](ROADMAP.md), [`V1_RELEASE_PLAN.md`](V1_RELEASE_PLAN.md).
