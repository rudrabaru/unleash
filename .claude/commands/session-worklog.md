---
description: Draft and append a concise, professional end-of-session worklog entry to docs/worklog.md.
allowed-tools: Read, Bash
---

You are closing out a work session. This command appends a concise daily summary to `docs/worklog.md`.

## What to do

1. Check current implementation progress and test execution results.
2. Review `docs/worklog.md` to ensure continuity from previous entries.
3. Draft one entry headed by the project Day and a milestone title, with the actual
   current date on the same line — e.g. `## Day N — <Milestone Title> (YYYY-MM-DD)`.
   The entry has exactly three parts:
   - **Done:** what was actually completed this session, evidenced by real diffs/commits
     — not intentions or plans. High-level professional bullets; never low-level code
     snippets, line numbers, or raw file-path listings.
   - **Left mid-flight:** anything incomplete, half-implemented, or stashed, and its
     current state. Write "nothing" if the tree is clean.
   - **Next step:** the single exact, concrete objective the next session should start
     with — specific enough that a cold-start read of this entry alone is enough to resume.
4. Append the entry to `docs/worklog.md`.
5. Show the developer the entry.

## Rules
- Run `git status --short` and `git diff` (staged and unstaged) to see the actual current working-tree state — do not rely on conversation memory of what was done, since that can drift from what's actually on disk.
- Never use developer identifiers (e.g., "Dev 1") in the worklog file name or content — the audio vertical is single-owner.
- Keep entries professional, concise, and focused on functional milestones and outcomes.
- Never commit `docs/worklog.md` as part of a code commit — it is local continuity material.

