# Rule: no hardcoded stub values

Every value the system reports must come from real computation, never from a constant chosen to fill a field or make a test pass.

**Forbidden:**

```python
# a fixed score that skips the real check
return DetectorResult(score=0.92, passed=True, reason="[STUB] checks passed")
# a hardcoded match that skips the speech recognizer
details.update({"phrase_matched": True, "words_detected": ["walnut", "lantern"]})
# an advisory score without running the heuristic
details.update({"voice_authenticity_score": 0.88, "av_alignment_score": 0.85})
# a threshold with no derivation
SCORE_THRESHOLD = 0.7
```

**Required:**

1. If something cannot be measured, return `score=None` (and exclude it from fusion); never a placeholder such as 0.5. Say why in `reason` or `details`.
2. A not-yet-implemented part is marked `[STUB]` in both the code comment and the module docstring, and it must not contribute to any score.
3. A threshold or divisor needs a comment citing where it came from (a measurement, a decision-log entry) or `[UNCALIBRATED]` when it is a starting guess.
4. Test-only constants stay in tests.

A plausible-looking numeric score that is not labelled is a bug, not a style issue.
