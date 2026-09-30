# Rule: CI Dependency Sync

## The CI File Is Not a Constant Maintenance Target

`ci.yml` should **not** be edited in response to every CI failure. A CI failure means either:
1. The **code is broken** — fix the code, not CI.
2. The **CI config has a bug** — fix it once, properly.
3. A **new dependency was added to `requirements-audio.txt`** without updating CI — see the rule below.

## The One Rule That Prevents CI Drift

> **Any commit that modifies `requirements-audio.txt` must also verify that `ci.yml` still works correctly.**

Specifically:
- If a package is **added** to `requirements-audio.txt`: the dynamic smoke test in `ci.yml` will pick it up automatically (no edit needed) UNLESS it is a special-case package (like `silero-vad` or `torchaudio`) that has a non-standard import name or requires a fallback. In that case, add handling in the `SKIP` block in `ci.yml`'s smoke test.
- If a package is **removed** from `requirements-audio.txt`: verify the smoke test won't try to import it (it reads `requirements-audio.txt` dynamically, so this is already handled automatically).

## What Requires a CI Edit

| Event | CI Edit Required? | What to Do |
|---|---|---|
| New generic package added to `requirements-audio.txt` | **No** | Dynamic smoke test handles it automatically |
| New special-case package with non-standard import name | **Yes** | Add to `SKIP` set in the smoke test |
| New package that requires a system-level install (like `ffmpeg`) | **Yes** | Add an `apt-get install` step |
| Stage 2/3/4 dependencies added | **No** | Dynamic smoke test handles them automatically |
| Code bug causes test to fail | **No** | Fix the code |

## The Authority

The canonical check after adding any new stage's dependencies is:
1. Add the package to `requirements-audio.txt`
2. Run `grep -E '^[A-Za-z]' backend/requirements-audio.txt` to confirm it's a clean line
3. The CI smoke test will automatically import it on the next push — no `ci.yml` edit needed
