# Rule: Feature / Stage Start Protocol

When the user describes a new feature or stage to implement in 1-2 lines, always follow this protocol before writing any code.

## Step 1 — Load Context First

Before responding, read these files in order:
1. `docs/unleash_project_plan.md` — the authoritative specification
2. `docs/unleash_team_companion_guide.md` — implementation detail and tooling choices
3. `.claude/context/audio-pipeline/stage-specifications.md` — for any audio-related feature
4. `docs/worklog.md` — to understand where the project currently stands
5. `CLAUDE.md` — team boundaries, 4-key contract, gate types

## Step 2 — Locate the Feature

Search `docs/unleash_project_plan.md` for the feature/stage by name and keyword.

### If FOUND in the project plan:
Generate a structured session-opening prompt (same format as `.claude/commands/start-feature.md`) that includes:
- Precise goal statement grounded in the project plan
- Stage spec: tools, gate type, acceptance criteria, dependencies
- Boundaries: ownership map, no-commit-without-approval, ask-before-assuming

### If NOT FOUND in the project plan:
**STOP. Do not write any code.**

Tell the user:
> "I searched `docs/unleash_project_plan.md` and this feature is not in the approved plan. Before I proceed, please confirm: (1) Is this a new addition? (2) Should I treat it as a prototype? (3) Which section should it fall under?"

Wait for confirmation before proceeding.

## The Rule

> **Never begin implementing a feature without first confirming it exists in the project plan or receiving explicit user authorization.**

This applies even if the feature "sounds obvious" or "fits the architecture." The project plan is the authority. If it is not there, stop and ask.
