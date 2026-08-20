---
description: Draft and append an end-of-session worklog entry (done / left mid-flight / next step) to docs/worklog-dev1.md, based on actual git state — not assumptions.
allowed-tools: Read, Bash
---

You are closing out a work session per the Unleash agentic development guide (Part 5, "End of every work session" ritual). This is the one command in this workspace whose entire purpose is to *write* something — every other command in `.claude/commands/` is report-and-wait-only; this one is the intentional exception.

## What to do

1. Run `git status --short` and `git diff` (staged and unstaged) to see the actual current working-tree state — do not rely on conversation memory of what was done, since that can drift from what's actually on disk.
2. Run `git log --oneline -10` (and, if `docs/worklog-dev1.md` already has a previous entry, read it) to understand what's already been committed since the last worklog entry, for continuity.
3. Draft a dated entry (use the actual current date) with three parts:
   - **Done:** what was actually completed this session, evidenced by real diffs/commits — not intentions or plans.
   - **Left mid-flight:** anything incomplete, half-implemented, or stashed, and its current state.
   - **Next step:** the exact, concrete thing the next session should start with — specific enough that a cold-start read of this entry alone is enough to resume.
4. Append the entry to `docs/worklog-dev1.md` (create the file with a one-line header if it doesn't exist yet — this file is gitignored via the repo's existing `/docs/` exclusion, so it's local-only, personal continuity material, not team-shared spec).
5. Show the developer exactly what was written.

## Rules

- Never fabricate a "done" item that isn't evidenced by an actual diff, commit, or file change you can point to.
- Never commit `docs/worklog-dev1.md` as part of a code commit — it's intentionally outside version control.
- If nothing meaningful happened this session (pure research/reading, no changes), say so plainly in the entry rather than padding it out.
