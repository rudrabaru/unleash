---
description: Analyze working tree changes and generate a precise, professional commit message in plain English representing only what was logically implemented.
allowed-tools: Read, Grep, Glob, Bash
---

You are generating a professional, clear, and logically accurate Git commit message based on the actual working-tree diffs.

## Instructions

1. Run `git status -s` and `git diff` (including untracked files) to inspect all changed and added files.
2. Understand the logical changes across all files:
   - Identify what capability, logic, or bugfix was implemented.
   - Trace how modules, utilities, schemas, and tests connect.
3. Structure the commit message:
   - **Header**: `<type>(<scope>): <concise active-voice summary under 72 chars>`
     - Types: `feat`, `fix`, `refactor`, `test`, `chore`, `docs`.
     - Scope: e.g. `audio`, `frontend`, `backend`, `deps`.
   - **Body**: Bulleted list in plain English explaining:
     - The core functional changes and algorithms implemented.
     - Why specific architectural or security choices were made.
     - New tests added and test suite verification results.
   - **Constraints**:
     - Do NOT use vague phase/stage jargon (e.g. avoid "Implement Stage 1", "Day 9 changes", or "update files").
     - Represent strictly what is logically implemented in the specific files.
     - Keep descriptions direct, professional, and accessible.
