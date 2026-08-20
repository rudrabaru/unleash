# AV Alignment Interface Agreement — ⚠️ BLOCKED / NOT YET AGREED

**Status: placeholder. This document is intentionally blank pending the Day 19 design session between Dev 1 and Dev 2.**

Per the root `CLAUDE.md` (Section E) and the agentic development guide: neither Dev 1 nor Dev 2 should implement Stage 4 (AV Temporal Alignment) beyond a stub that accepts both inputs and returns a hardcoded score until this document is filled in with the actual agreed format.

## What gets decided at the Day 19 session

1. **Lip openness series format** (produced by Dev 2's MediaPipe processing loop, consumed by Dev 1's Stage 4):
   - Exact data structure — list of tuples? dict keyed by frame index? numpy array? *(TBD)*
   - Confirmed fields: frame index, normalized lip openness ratio (vertical distance between upper/lower lip ÷ face height), plus video fps to convert frame indices to timestamps.

2. **Word timestamp format** (produced by Dev 1's own faster-whisper output, used internally by Dev 1's Stage 4 — but must be cross-checked with Dev 2 since it's the other half of the alignment computation):
   - Confirmed shape from the project plan: list of `(word: str, start_seconds: float, end_seconds: float)`.
   - Anything Dev 2 needs to know about this shape to sanity-check the alignment logic gets recorded here too.

3. **Tolerance window:** ±300ms misalignment allowance is already agreed in the project plan (Section 5.5) — not up for renegotiation at Day 19 unless evaluation evidence later suggests otherwise.

## After the session

Replace this entire file's content with the actual agreed format (with a real example payload for each side), then:
- Update `stage-specifications.md`'s Stage 4 section to reference the finalized format instead of "subject to agreement"
- Update root `CLAUDE.md` Section E if the high-level description of the exchange changes
- Only then begin the real Stage 4 implementation (Days 23–24 per the project plan)
