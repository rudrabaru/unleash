# Rule: Dependency Tracking & Dead Code

This rule applies continuously. Run the `/dead-code-audit` command at these specific trigger points:

## When to Audit

1. **After every stage implementation** — after Stage 1, Stage 2, Stage 3, Stage 4
2. **Before opening an integration PR** — at Day 22 and Day 30 milestone days
3. **When adding or removing any import** from `requirements.txt` or `requirements-audio.txt`
4. **When explicitly asked** by the user

## What Counts as Dead Code (scoped to the audio pipeline)

- Functions defined in `backend/app/modules/audio/` that are never called by `process_audio_pipeline()` in `__init__.py` or by each other
- Imports in any audio module file that are never actually used in that file
- Variables assigned but never read
- Packages listed in `requirements-audio.txt` that no file under `backend/app/modules/audio/` actually imports
- Prototype files or stub files left over from exploratory work (anything not part of the real implementation)

## What NOT to Remove

- Functions/imports needed by tests in `backend/tests/`
- Code marked with a comment like `# Stage N stub — not yet implemented` (these are intentional placeholders)
- Anything in `backend/prototypes/` that is documented in `NOTES.md` as retained for upcoming stages

## The Process

Always use `/dead-code-audit` for this — do not do it ad-hoc. The command produces a structured report. Deletions only happen after user approval of the report. Always run `pytest backend/tests -v` after any deletion to verify nothing broke.
