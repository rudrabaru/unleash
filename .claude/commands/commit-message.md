---
description: Read the working-tree changes and write a precise conventional commit message for what was actually implemented.
allowed-tools: Read, Grep, Glob, Bash
---

Write a commit message from the real diff.

1. Run `git status -s` and `git diff` (staged and unstaged, plus untracked files).
2. Work out what was implemented or fixed and why; follow how modules, tests and docs connect.
3. Format:
   - Header: `<type>(<scope>): <active-voice summary under 72 characters>`; types `feat`, `fix`, `refactor`, `perf`, `test`, `chore`, `docs`, `build`.
   - Body: at most 5 bullets in plain English covering the concrete behaviour, the reason for non-obvious choices, and the tests added or run.
4. Do not use vague labels ("various fixes", "WIP", "update files") or project-internal numbering. Describe only what the diff contains.
5. Show the message; commit only if the owner asks.
