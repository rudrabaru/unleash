# Rule: repo hygiene

- Run `/dead-code-audit` before opening a pull request and after removing or adding a dependency. Delete only what the owner approves, then run the tests.
- `backend/requirements.txt` is the one runtime list and `requirements-dev.txt` the test tools. Edit `.github/workflows/ci.yml` only for a system package or a CI bug, never to hide a failing test.
- Missing tracked test fixtures must fail the test, not skip it. A skip needs a reason that is not "file missing".
- Record findings that change a decision or a threshold in `.claude/context/decisions.md`, and still-true gotchas in `.claude/context/audio-pipeline/known-tricky-spots.md`. These live in git; the private `docs/` folder is optional background only.
- Write commit messages with `commit_message_generation.md`. Do not commit generated data, checkpoints, databases or `temp_uploads/`.
