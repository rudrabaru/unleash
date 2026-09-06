---
description: Turn a 1-2 line feature description into a context-loaded implementation session prompt after checking docs/unleash_project_plan.md; never writes code.
argument-hint: "<1-2 line feature or stage description>"
allowed-tools: Read, Grep, Glob
---

Generates a complete, context-loaded implementation session from a 1-2 line feature description. Never writes code — outputs a structured prompt you can immediately use to start implementing.

## Step 1 — Understand the Description

Read the user's 1-2 line feature/stage description carefully. Extract:
- The feature or stage name (e.g., "Stage 2 — Phrase Compliance", "mic capture UI", etc.)
- The primary domain (audio, visual, frontend, backend-core)
- Any specific constraints or parameters mentioned

## Step 2 — Search the Project Plan

Read `docs/unleash_project_plan.md` in full. Search for the feature/stage by name or by its description keywords.

Also read the other relevant docs for context:
- `docs/unleash_team_companion_guide.md` — for stage-level implementation detail, tooling choices, and edge case notes
- `docs/unleash_pipeline_visualization.md` — for understanding how this feature fits into the pipeline flow
- `.claude/context/audio-pipeline/stage-specifications.md` — for audio-specific stage specs (if the feature is audio-related)

## Step 3 — Branch: Found or Not Found

### If the feature/stage IS in the project plan:

Produce a structured session-opening prompt in the following format:

```
Day/Phase: Day <N>, Phase <P>.
Context: Read CLAUDE.md and .claude/context/audio-pipeline/ before we start.
Where I left off: <summarize the last completed stage from docs/worklog.md or the user's description>

Today's goal: <restate the feature in one precise sentence grounded in the project plan>

Relevant spec:
  - Stage/Feature location in project plan: Section <X>, Page <Y>
  - Dependencies on other stages or developers: <list>
  - Hard gate or advisory: <state explicitly>
  - Tools/models specified: <list from the project plan>
  - Acceptance criteria: <list from the project plan or derive from spec>

Boundaries:
  - Do not touch Dev 2/Dev 3 module folders.
  - Report-only on all checks (/schema-check, /graceful-failure-audit) unless told to fix.
  - Never commit or push without explicit go-ahead.
  - If ambiguous at any point: ask, don't assume (Rule J1 in CLAUDE.md).
```

### If the feature/stage is NOT in the project plan:

Report back to the user:

```
⚠️  I searched docs/unleash_project_plan.md and could not locate a specification for:
"<the user's feature description>"

This feature does not appear to be part of the approved project plan.

Before proceeding, please confirm:
1. Is this a new addition you want to add to the plan?
2. Should I treat this as an exploratory prototype (not production code)?
3. Which section of the plan should this fall under?

I will not begin implementation until you confirm.
```

## Step 4 — Output Only

Do NOT write any code. Do NOT modify any files. Output the structured session prompt (or the not-found warning) only, and wait for the user to tell you to proceed.
