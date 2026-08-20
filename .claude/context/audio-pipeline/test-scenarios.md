# Audio Pipeline — Test Scenarios

Source of truth: Project Plan v2.1, Section 7 Phase 4. These are the scenarios the audio vertical must be validated against before evaluation sign-off. Run at least 8–10 recordings per scenario; log results to CSV; compute TAR/FAR/FRR from the results (see root `CLAUDE.md` Section F for targets).

| # | Scenario | How to Generate | Expected Result |
|---|---|---|---|
| 1 | Genuine speech — correct phrase | Speak "7-4-2" (or whatever the session's actual challenge number is) clearly during the challenge window | `VERIFIED` (Stages 1 & 2 pass) |
| 2 | Genuine speech — accent variant | A different speaker (different accent) says the correct phrase | `VERIFIED` — if this fails, it's evidence for threshold tuning, not a code bug |
| 3 | Genuine speech — quiet or fast | Speak the correct phrase quickly or quietly | `VERIFIED`; tune Stage 1 duration threshold or Stage 2 matching if it fails |
| 4 | Silence — mic muted | Complete the visual challenge, say nothing | `FAILED` at Stage 1 (speech gate) |
| 5 | Wrong phrase | Say "one two three" instead of the actual challenge number | `FAILED` at Stage 2 (phrase compliance) |
| 6 | Background TV / podcast | Sit silently; play speech from a phone speaker near the mic | `FAILED` at Stage 2 (wrong phrase relative to *this* session's challenge) |
| 7 | Replay with ambient audio | Play a pre-recorded video with speech in the background | `FAILED` at Stage 2 — the replayed phrase won't match this session's freshly-issued challenge number |
| 8 | TTS injection | Play a TTS clip speaking the *correct* number into the mic | Stage 2 may legitimately pass (correct digits were said). Stage 3 (voice authenticity) should flag it as advisory-low. **Document the actual result honestly — do not force Stage 2 to fail just to make the scenario "look right."** |
| 9 | Non-speech audio | Play music near the mic | `FAILED` at Stage 1 (no speech detected) |
| 10 | Whisper / very low volume | Whisper the correct phrase very quietly | Document the actual result; tune Stage 1's threshold if it's incorrectly gating out genuine quiet speech |

**Honesty requirement:** For scenario 8 in particular, and for any scenario where results are marginal, log what actually happened rather than what "should" happen. The Phase 4 deliverable is an honest TAR/FAR/FRR table with documented threshold-tuning decisions, not a scenario table forced to look perfect. This directly informs how Stage 3's spectral heuristic is judged for the technical summary.

**Threshold tuning driven by these results (Phase 4, Dev 1's responsibility):**
- Stage 1 `speech_duration` threshold (currently 2.0s)
- Stage 2 digit-matching tolerance (currently 2-of-3 digits)
- Stage 3 spectral threshold, if it's incorrectly flagging genuine speech as inauthentic

Document every threshold change here (update the corresponding value in `stage-specifications.md`) and, if it changes hard-gate behavior, in the root `CLAUDE.md` too.
