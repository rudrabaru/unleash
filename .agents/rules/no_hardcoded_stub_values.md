# Rule: No Hardcoded Stub Values

## Intent

Every piece of code written in this repository must reflect the **real, dynamic state** of the system. Hardcoded stub values written only to satisfy a feature requirement or make tests pass are a form of technical debt that silently destroys the security and correctness guarantees Unleash depends on.

This rule applies to both **Antigravity IDE** and **Claude Code** sessions, in every prompt, without exception.

---

## What Is Prohibited

**Hardcoded stubs masquerading as real outputs.** Examples:

```python
# ❌ FORBIDDEN: Stub score that bypasses real Stage 2 logic
return DetectorResult(score=0.92, passed=True, reason="[STUB: Stages 2-4 passed]")

# ❌ FORBIDDEN: Hardcoded phrase match that skips actual STT
combined_details.update({"phrase_matched": True, "digits_detected": [7, 4, 2]})

# ❌ FORBIDDEN: Hardcoded advisory score without running Stage 3
combined_details.update({"voice_authenticity_score": 0.88, "av_alignment_score": 0.85})

# ❌ FORBIDDEN: Magic number threshold with no derivation
SCORE_THRESHOLD = 0.7  # where did this come from?
```

**This pattern is acceptable only as a named, documented, temporary stub** — and ONLY if:
1. The field is explicitly marked `[STUB]` in the code comment **and** the module docstring.
2. The stub is for a **not-yet-implemented stage** (e.g., Stage 3 or 4 while Stage 2 is being built).
3. It will be replaced before that stage's handoff milestone.

---

## What Is Required

1. **All computed values must come from real computation.** If a score is produced, it must be derived from actual model output or algorithm results — not a constant.

2. **If a stage is not yet implemented, say so explicitly.** Return a clearly labeled stub with `reason="[STUB] Stage N not yet implemented"`. Do NOT return a plausible-looking numeric score that hides the fact that no computation occurred.

3. **No magic numbers without derivation.** If you write a threshold (`2.0`, `0.67`, `2/3`), it must be explained in a code comment citing the project plan or a measured evaluation result.

4. **Advisory stubs in the pipeline must not influence the final `score` field.** The audio module's `score` must ONLY reflect stages that have been genuinely implemented. If Stage 3 is a stub, exclude it from the score or set score based only on Stage 2's real output.

---

## Enforcement

- Before writing any value as a constant or hardcoded literal, ask: *"Is this real computation, or am I just filling a field to satisfy a test or type signature?"*
- If the answer is the latter, either implement the real logic or explicitly mark it as a named stub with a `[STUB]` comment and a corresponding `TODO` in the module docstring.
- Any code review or session audit that finds a hardcoded plausible-looking numeric score (not labeled `[STUB]`) should be treated as a bug, not a style issue.
