# Unleash Workspace Rules (Antigravity IDE & Claude Code)

Welcome to the Unleash codebase.

## 1. Project Specifications
- The authoritative project reference is defined in [CLAUDE.md](file:///d:/Projects/Unleash/CLAUDE.md). Adhere strictly to the **4-Key Contract** (`DetectorResult`), CPU-only inference, and team ownership boundaries (Dev 1 = Audio).

## 2. Permanent Session Rules (Mandatory — No Exceptions)
- **Ask Before Assuming:** If there is ANY ambiguity in the request, stop and ask the user directly before writing any code or modifying any file. Consolidate all open questions into one message. Never make assumptions to fill gaps. See [`.agents/rules/ask_before_assuming.md`](file:///d:/Projects/Unleash/.agents/rules/ask_before_assuming.md).
- **Dead Code Tracking:** After every stage implementation and before any integration PR, run `/dead-code-audit` to identify dead functions, unused imports, and dependency drift. Only delete after explicit user approval. Verify with `pytest` after each deletion. See [`.agents/rules/dead_code_tracking.md`](file:///d:/Projects/Unleash/.agents/rules/dead_code_tracking.md).

## 3. Slash Commands
- Custom workflows and commands are defined in [`.claude/commands/`](file:///d:/Projects/Unleash/.claude/commands/).
- Whenever a slash command (e.g., `/schema-check`, `/graceful-failure-audit`, `/commit-message`, `/session-worklog`, `/stage-done`, `/threshold-sweep`, `/latency-benchmark`, `/scenario-runner`, `/stub-interface-check`, `/dead-code-audit`) is requested, read and execute the prompt in the corresponding `.claude/commands/<command-name>.md` file.

## 3. Audio Pipeline Domain Context
- For all audio pipeline implementation, testing, and debugging, refer to [`.claude/context/audio-pipeline/`](file:///d:/Projects/Unleash/.claude/context/audio-pipeline/).

## 4. Documentation & Commit Guidelines
- Follow [`.agents/rules/document_observations.md`](file:///d:/Projects/Unleash/.agents/rules/document_observations.md) to record observations in [docs/audio_pipeline_observations.md](file:///d:/Projects/Unleash/docs/audio_pipeline_observations.md) after milestones.
- Follow [`.agents/rules/commit_message_generation.md`](file:///d:/Projects/Unleash/.agents/rules/commit_message_generation.md) when formulating commit messages.
