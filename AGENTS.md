# Unleash Workspace Rules (Antigravity IDE & Claude Code)

Welcome to the Unleash codebase.

## 1. Project Specifications
- The verbal challenge is a **5-word phrase** (Stage 2 gate: ≥ 4 of 5 words, per-word similarity ≥ 0.8). Any text that still says "3-digit" or "2 of 3" is stale — fix it or flag it.
- The authoritative project reference is defined in [CLAUDE.md](file:///d:/Projects/Unleash/CLAUDE.md). Adhere strictly to the **4-Key Contract** (`DetectorResult`), CPU-only inference, and team ownership boundaries (Dev 1 = Audio).

## 2. Permanent Session Rules (Mandatory — No Exceptions)
- **Ask Before Assuming:** If there is ANY ambiguity in the request, stop and ask the user directly before writing any code or modifying any file. Consolidate all open questions into one message. Never make assumptions to fill gaps. See [`.agents/rules/ask_before_assuming.md`](file:///d:/Projects/Unleash/.agents/rules/ask_before_assuming.md).
- **Dead Code Tracking:** After every stage implementation and before any integration PR, run `/dead-code-audit` to identify dead functions, unused imports, and dependency drift. Only delete after explicit user approval. Verify with `pytest` after each deletion. See [`.agents/rules/dead_code_tracking.md`](file:///d:/Projects/Unleash/.agents/rules/dead_code_tracking.md).
- **CI Dependency Sync:** Never edit `ci.yml` in response to a code bug. Only edit it when adding a special-case package with a non-standard import name. The smoke test is dynamic and self-maintains. See [`.agents/rules/ci_dependency_sync.md`](file:///d:/Projects/Unleash/.agents/rules/ci_dependency_sync.md).
- **Feature Start Protocol:** When the user describes a new feature or stage in 1-2 lines, always read `docs/unleash_project_plan.md` first. If the feature is in the plan, generate a structured session prompt. If it is NOT in the plan, stop and ask for confirmation before writing any code. See [`.agents/rules/feature_start_protocol.md`](file:///d:/Projects/Unleash/.agents/rules/feature_start_protocol.md).
- **No Hardcoded Stub Values:** Never write hardcoded constants, magic numeric scores, or fabricated pass/fail values to satisfy a feature requirement or make a test pass. Every computed value must come from real algorithm or model output. If a stage is not yet implemented, label it `[STUB]` explicitly in both the code comment and the module docstring — never return a plausible-looking numeric result that hides the fact no real computation occurred. See [`.agents/rules/no_hardcoded_stub_values.md`](file:///d:/Projects/Unleash/.agents/rules/no_hardcoded_stub_values.md).
- **SOLID Audio Architecture:** Maintain strict modularity and separation of concerns across `backend/app/modules/audio/`. Keep runner functions small (<40 lines), route all WAV decoding through `_io.py`, isolate score math in helpers, and ensure LSP/4-Key Contract adherence. See [`.agents/rules/solid_audio_pipeline.md`](file:///d:/Projects/Unleash/.agents/rules/solid_audio_pipeline.md).

## 3. Slash Commands
- Custom workflows and commands are defined in [`.claude/commands/`](file:///d:/Projects/Unleash/.claude/commands/).
- Whenever a slash command is requested, read and execute the prompt in the corresponding `.claude/commands/<command-name>.md` file.
- **Available commands:** `/schema-check`, `/graceful-failure-audit`, `/commit-message`, `/session-worklog`, `/stage-done`, `/threshold-sweep`, `/latency-benchmark`, `/scenario-runner`, `/stub-interface-check`, `/dead-code-audit`, `/start-feature`, `/solid-audit`

## 4. Audio Pipeline Domain Context
- For all audio pipeline implementation, testing, and debugging, refer to [`.claude/context/audio-pipeline/`](file:///d:/Projects/Unleash/.claude/context/audio-pipeline/).
- Context files: `README.md`, `stage-specifications.md`, `automation-workflow.md`, `known-tricky-spots.md`, `test-scenarios.md`, `integration-checklist.md`, `av-alignment-interface.md`, `decisions.md` (team decision log — read before changing any gate, threshold, schema or scope)
- Release roadmap: [ROADMAP.md](ROADMAP.md) (long-term, to the final deliverable) and [V1_RELEASE_PLAN.md](V1_RELEASE_PLAN.md) (the one-day v1). CLAUDE.md Section K is the summary.

## 5. Claude Code Hooks & Subagents
- **Hooks** (fire automatically in every Claude Code session): [`.claude/hooks/ownership_guard.py`](file:///d:/Projects/Unleash/.claude/hooks/ownership_guard.py) blocks edits to Dev 2/3 module paths and `backend/app/core/` · [`.claude/hooks/schema_guard.py`](file:///d:/Projects/Unleash/.claude/hooks/schema_guard.py) blocks edits to `backend/app/schemas/` · [`.claude/hooks/syntax_check.py`](file:///d:/Projects/Unleash/.claude/hooks/syntax_check.py) runs `py_compile` after every `.py` save (Edit/Write/MultiEdit). Wired in [`.claude/settings.json`](file:///d:/Projects/Unleash/.claude/settings.json). For Antigravity IDE sessions, the equivalent text rules are in [`.agents/rules/ownership_and_schema_guard.md`](file:///d:/Projects/Unleash/.agents/rules/ownership_and_schema_guard.md).
- **Subagents** (delegate to for isolated tasks): `audio-schema-validator` (schema compliance audit) · `test-runner-reporter` (structured pytest summary). Defined in [`.claude/agents/`](file:///d:/Projects/Unleash/.claude/agents/).

## 6. Documentation & Commit Guidelines
- Follow [`.agents/rules/document_observations.md`](file:///d:/Projects/Unleash/.agents/rules/document_observations.md) to record observations in [docs/audio_pipeline_observations.md](file:///d:/Projects/Unleash/docs/audio_pipeline_observations.md) after milestones.
- Follow [`.agents/rules/commit_message_generation.md`](file:///d:/Projects/Unleash/.agents/rules/commit_message_generation.md) when formulating commit messages.

## 7. Cross-IDE Consistency
- This repo is used with both **Antigravity IDE** and **Claude Code**. Rules in `.agents/rules/` apply to both. Claude Code hooks in `.claude/hooks/` apply only within Claude Code sessions. The bridge for keeping both IDEs consistent is documented in [`.agents/rules/claude_bridge.md`](file:///d:/Projects/Unleash/.agents/rules/claude_bridge.md).
