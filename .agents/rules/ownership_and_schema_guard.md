# Ownership & Schema Guardrails (Antigravity IDE Parity)

These rules mirror the enforcement performed by Claude Code hooks in `.claude/hooks/`.
They apply unconditionally during Antigravity IDE sessions.

## 1. Team Ownership Boundaries (CLAUDE.md Section C)

**NEVER modify the following paths** without an explicit cross-team instruction from the user:

- `backend/app/modules/visual/` — **Dev 2 exclusive**
- `backend/app/modules/antispoof/` — **Dev 3 exclusive**
- `backend/app/api/v1/endpoints/eval.py` — **Dev 3 exclusive**
- `backend/app/core/` — **shared** (config + HMAC); changes require team agreement (CLAUDE.md Section G)
- `backend/app/api/v1/endpoints/sessions.py` — **split-owned** (Dev 2 creation logic / Dev 3 orchestration); touch only for an agreed cross-team change

If you find yourself about to edit one of these paths, STOP. Report to the user that the path is outside Dev 1's ownership boundary and ask for an explicit cross-team change instruction before writing any code.

## 2. Schema Change Hard Block (CLAUDE.md Section G)

**NEVER modify the following files** without explicit team authorization:

- `backend/app/schemas/detector.py`
- Any file in `backend/app/schemas/`

Per CLAUDE.md Section G: "Any change to the 4-key `DetectorResult` schema... must never happen without team discussion." If the user explicitly authorizes a schema change (i.e., team discussion has already happened), ask them to confirm once more before writing code.

## 3. Python Syntax Self-Check

After editing any `.py` file, mentally verify the edit does not introduce a syntax error. If uncertain, ask to run `python -m py_compile <file>` before proceeding.
