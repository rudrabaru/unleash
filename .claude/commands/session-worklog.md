---
description: Draft and append a concise, professional end-of-session worklog entry to docs/worklog.md.
allowed-tools: Read, Bash
---

You are closing out a work session. This command appends a concise daily summary to `docs/worklog.md`.

## What to do

1. Check current implementation progress and test execution results.
2. Review `docs/worklog.md` to ensure continuity from previous entries.
3. Draft an entry organized by project Day/Phase (e.g. `## Day N — <Milestone Title>`):
   - **Accomplished:** high-level, professional bullet points describing what was built, verified, or discovered. (Never include low-level code snippets, line numbers, or raw file path listings).
   - **Current State:** a 1-line high-level status of the vertical.
   - **Next Objective:** the single concrete objective for the next session.
4. Append the entry to `docs/worklog.md`.
5. Show the developer the entry. Draft a dated entry (use the actual current date) with three parts:
   - **Done:** what was actually completed this session, evidenced by real diffs/commits — not intentions or plans.
   - **Left mid-flight:** anything incomplete, half-implemented, or stashed, and its current state.
   - **Next step:** the exact, concrete thing the next session should start with — specific enough that a cold-start read of this entry alone is enough to resume.

## Rules
- Run `git status --short` and `git diff` (staged and unstaged) to see the actual current working-tree state — do not rely on conversation memory of what was done, since that can drift from what's actually on disk.
- Never use developer identifiers (e.g., "Dev 1") in the worklog file name or content — the audio vertical is single-owner.
- Keep entries professional, concise, and focused on functional milestones and outcomes.
- Never commit `docs/worklog.md` as part of a code commit — it is local continuity material.

