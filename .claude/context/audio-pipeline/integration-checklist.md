# Stage-Level Integration Checklist

Before any stage (or the full audio module) is declared "done" and handed to Dev 3's orchestrator, Claude must verify every item below. This is not a suggestion list — treat it as a gate on calling something finished.

- [ ] **Exact schema.** Does the function return the exact 4-key `DetectorResult` schema (`score`, `passed`, `reason`, `error`, optional `details`) — no renamed fields, no extra required fields?
- [ ] **Error semantics.** Is `error` populated when the stage fails internally, with `score` set to `null` in that case (never a numeric score alongside a non-null error)?
- [ ] **Graceful degradation.** Does the function handle a corrupt or empty audio file without raising an uncaught exception — returning a valid schema instance instead?
- [ ] **Hard gate behavior.** For Stages 1 and 2 specifically: does a failed gate set `passed = False` and halt the pipeline (skip remaining stages), rather than raising an exception or silently continuing?
- [ ] **Scenario coverage.** Has the module been exercised against at least 3 of the 10 scenarios in `test-scenarios.md`, with actual output recorded (not assumed)?

**When to run this checklist:** every time a stage moves from "implemented" to "ready to hand off" — explicitly Day 7 (stub), Day 21–22 (real Stages 1–3), and Day 23–24 (real Stage 4, post Day-19 unblock). Also re-run it any time a threshold or matching algorithm changes during Phase 4 evaluation tuning, since a threshold change can silently break the error/gate semantics above.
