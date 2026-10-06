# Audio test scenarios

The scenarios the audio checks must be evaluated against with recorded clips (8-10 recordings per scenario from at least 3 speakers for the full evaluation). Log results to a CSV and compute TAR/FAR/FRR from it (targets in `CLAUDE.md`). No recordings for the scenarios below exist yet except the single genuine take, so `/scenario-runner` and `/threshold-sweep` cannot be run meaningfully until they are recorded.

| # | Scenario | How to generate | Expected result |
|---|---|---|---|
| 1 | Genuine speech, correct phrase | Say the session's actual 5-word challenge clearly | passes the speech and phrase checks |
| 2 | Genuine speech, accent variant | A different speaker (different accent) says the phrase | passes; a failure here is evidence for threshold tuning, not necessarily a code bug |
| 3 | Genuine speech, quiet or fast | Speak the phrase quickly or quietly | passes; tune the speech duration threshold or the matching if it fails |
| 4 | Silence | Complete the visual challenge, say nothing | fails the speech check |
| 5 | Wrong phrase | Say 5 other words from the vocabulary | fails the phrase check |
| 6 | Background TV or podcast | Sit silently while speech plays near the microphone | fails the phrase check (wrong words for this session) |
| 7 | Replay with ambient audio | Play a recorded video with speech in the background | fails the phrase check (the replayed phrase will not match this session's challenge) |
| 8 | Text-to-speech injection | Play a synthetic voice saying the *correct* phrase into the microphone | the phrase check may legitimately pass. Report the actual result of the phrase check and the voice check honestly; do not force a failure |
| 9 | Non-speech audio | Play music near the microphone | fails the speech check |
| 10 | Whisper or very low volume | Whisper the correct phrase | report the actual result; tune the speech threshold if genuine quiet speech is gated out |

**Honesty requirement:** for scenario 8 and any marginal result, log what actually happened rather than what should happen. The deliverable is an honest results table with documented threshold decisions, not a table forced to look perfect.

**Thresholds these results tune** (change only with recorded evidence, and update `audio-checks.md` and the decision log in the same commit): the speech duration (2.0 s), the phrase check's 4-of-5 count, 0.8 similarity and 0.5 per-word confidence, and the voice-authenticity heuristics (still uncalibrated).

**Checks every audio change must keep passing:** the result has exactly the 4 keys; `error` set means `score` is `None`; a corrupt or empty file returns a valid result instead of raising; a failed must-pass check sets `passed=False` and skips the later checks.
