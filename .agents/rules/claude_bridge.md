# Dual-IDE Bridge: Antigravity IDE & Claude Code Integration

This workspace is designed to be fully dual-compatible with both **Antigravity IDE** (Gemini 3.1 Pro, Gemini 3.7 Flash, Claude Sonnet 3.7) and **Claude Code**.

## Core Operational Rules for Antigravity IDE Models

1. **Inviolable Project Specifications (`CLAUDE.md`)**:
   - Always read and adhere to [CLAUDE.md](file:///d:/Projects/Unleash/CLAUDE.md) before making architectural changes or implementing detector modules.
   - Respect the **4-Key Contract** (`DetectorResult` schema), Module Ownership boundaries (Dev 1 for Audio), Hard Gate definitions, and CPU-only constraints.

2. **Slash Commands Integration (`.claude/commands/`)**:
   - When the user runs or references any slash command (e.g., `/schema-check`, `/graceful-failure-audit`, `/commit-message`, `/session-worklog`, `/stage-done`, `/threshold-sweep`, `/latency-benchmark`, `/scenario-runner`, `/stub-interface-check`), **you must read the corresponding markdown file in `.claude/commands/<command-name>.md`** and execute the full workflow defined in that prompt.

3. **Domain Context (`.claude/context/`)**:
   - When working on the audio pipeline or related tests/features, actively reference all documents under [`.claude/context/audio-pipeline/`](file:///d:/Projects/Unleash/.claude/context/audio-pipeline) including:
     - `stage-specifications.md`
     - `known-tricky-spots.md`
     - `test-scenarios.md`
     - `integration-checklist.md`
     - `av-alignment-interface.md`
     - `automation-workflow.md`

4. **Continuous Learning & Rules (`.agents/rules/`)**:
   - Always adhere to all rules defined in [`.agents/rules/`](file:///d:/Projects/Unleash/.agents/rules/), including:
     - `document_observations.md`: Record technical findings in plain English in `docs/audio_pipeline_observations.md` after every major milestone.
     - `commit_message_generation.md`: Generate high-standard, conventional commit messages summarizing logical changes.
