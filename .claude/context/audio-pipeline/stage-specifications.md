# Audio Pipeline — Stage Specifications

Source of truth: Project Plan v2.1 Section 5. This document restates it in a form optimized for Claude Code to act on directly. If this document and the project plan ever disagree, treat that as a bug — flag it, don't silently pick one.

**Integration contract:** The audio module exposes one async entrypoint in `backend/app/modules/audio/__init__.py`: `process_audio_pipeline(media_path: str, challenge_phrase: str) -> DetectorResult`. Internally it runs Stages 1–4 in sequence and folds the result into a single `DetectorResult` (the 4-key contract, see root `CLAUDE.md` Section B). Dev 3's orchestrator calls only this one function — it does not call individual stages directly.

**Current implementation status:** Stages 1, 2, and 3 are fully implemented (`[REAL]`); Stage 4 is an honest `[STUB]` (returns `score=None`, never gates) pending the Day 19 interface agreement. The module is already wired into `backend/app/api/v1/endpoints/sessions.py`'s background-task flow.

---

## Pipeline Order

```
[.webm blob] → ffmpeg extraction → 16kHz mono WAV
  → Stage 1: Speech Gate (silero-vad)              [HARD GATE]
  → Stage 2: Phrase Compliance (faster-whisper)     [HARD GATE]
  → Stage 3: Voice Authenticity (librosa)           [advisory]
  → Stage 4: AV Temporal Alignment (Whisper × MediaPipe lip data)  [advisory]
  → audio_result { score, passed, reason, error, details }
```

Stage 1 and Stage 2 gate the pipeline: if either fails, stop immediately and return `passed: false` without running Stages 3–4. Stages 3 and 4 always run if Stages 1–2 passed, and never change `passed` — they only affect the advisory `score`.

---

## Audio Extraction (pre-Stage 1)

- Input: the single `.webm` blob (video + Opus audio combined) uploaded by the frontend.
- Tool: **ffmpeg invoked as a subprocess**, not a Python ffmpeg-wrapper library.
- Output: WAV resampled to **exactly 16kHz mono**, regardless of what sample rate the browser actually recorded at. Never trust the browser's `sampleRate` constraint hint — always force-resample server-side.
- This step is shared infrastructure conceptually (both Stage 1 and Stage 2 need 16kHz mono PCM) but lives inside the audio module — it is not the same as Dev 3's video frame-extraction utility.

---

## Stage 1 — Speech Gate (VAD)

**Purpose:** Cheapest, fastest check. Eliminates non-speech submissions before heavier compute runs.

**Tool:** `silero-vad` (primary). If it has import/build issues (known Windows problem — see `known-tricky-spots.md`), fall back to `webrtcvad`. This fallback is pre-approved; it does not need a team discussion.

**Hard gate logic:**
- `speech_detected == False` → `passed = False`, stop. Reason: `"No speech detected"`.
- `speech_duration < 2.0 seconds` → `passed = False`, stop. Reason should say why (duration too short for a 3-digit challenge).
- The `2.0` second threshold is a starting point, tunable in Phase 4 based on evaluation evidence — document any change here and in root `CLAUDE.md` if it affects gate behavior broadly.

**Output carried to later stages:** speech segments with start/end timestamps (seconds). Reused conceptually by Stage 4's tolerance window, though Stage 4 primarily uses Whisper's own word-level timestamps.

---

## Stage 2 — Phrase Compliance (STT + Matching)

**Purpose:** The core audio security control — verify the user said the server-issued challenge number.

**Tool:** `faster-whisper`, `tiny` model (~39MB). **Must be loaded once at process/module init, never per-request** (this is the #1 known gotcha — see `known-tricky-spots.md`). Always extract word-level timestamps; faster-whisper returns them natively — never discard them, Stage 4 needs them.

**Matching logic — do not use exact transcript matching:**
1. Extract digit words from the transcript (handle digit-by-digit: "seven, four, two"; combined: "seven forty-two"; full number: "seven hundred forty-two"; hesitation: "seven... four... two").
2. Reconstruct a digit sequence from what was recognized.
3. Compare against the challenge's actual digit sequence.
4. **Match threshold: at least 2 of 3 digits correct → `passed = True`.** 0 or 1 digits correct → `passed = False` (hard gate).
5. Exact string matching will produce unacceptable false-reject rates due to ASR noise/accent/hesitation — this is a known, deliberate design decision, not a shortcut to fix later.

**Output:** full transcript, word-level timestamps list `(word, start_seconds, end_seconds)`, `phrase_matched: bool`, `digits_detected: list`.

---

## Stage 3 — Voice Authenticity (Spectral Analysis)

**Purpose:** Advisory-only signal flagging TTS injection or replayed audio through a speaker. Never gates the pipeline.

**Approach:** `librosa` FFT analysis over short windows of the speech segments — no ML model, pure heuristics:
- Noise floor consistency (live mics have a variable, non-zero noise floor; TTS/injected audio is often artificially clean)
- Formant energy distribution (human speech shows natural formant variation; pure TTS shows unnatural spectral regularity)
- Breathing artifacts between words (subtle, present in live speech)

Produces a `0.0–1.0` advisory score. **Timebox implementation to 2 days max** — if the heuristic isn't working well by then, document the finding honestly and move on; do not let this stage block Stage 4 or the overall handoff.

**Calibration status: `[UNCALIBRATED]` (Phase 4).** The heuristics are real computations on real
audio — nothing here is stubbed — but every threshold, divisor and weight in `_voice_authenticity.py`
(flux divisor `10.0`, hf_ratio divisor `0.15`, the noise-floor `cov`/`mean_rms` divisors, the
`0.30/0.45/0.25` weights, the `0.5` neutral fallback, the `0.1/0.2` buckets) is an initial guess
never fitted to a labelled recording set. Measured against the only labelled fixtures available
(2 genuine, 1 TTS), the composite shows **no separation** between genuine and TTS speech: 0.723 and
0.769 genuine vs 0.732 TTS. The spectral-flux term saturates to 1.0 on every real recording and the
HF-rolloff term runs opposite to its documented direction. **No value has been changed**, because
`test-scenarios.md` requires 8–10 recordings per scenario and we have 3 usable data points from 2
sources — see `docs/audio_pipeline_observations.md` §7 for the evidence and the recording set needed
to unblock calibration. Do not cite these numbers as tuned.

**Degraded-run honesty:** branches that cannot perform a real measurement (librosa unavailable,
audio shorter than one 512-sample STFT frame, no inter-speech silence) still return a numeric score
— Stage 3 is advisory and must not disturb the pipeline — but flag `details["degraded"] = true` with
a `degraded_reason`, so a placeholder is never mistaken for a measurement in the eval store.

**Future upgrade path (out of scope now):** `speechbrain/aasist` (ASVspoof-trained). Design this stage's interface so swapping the heuristic for AASIST later requires no changes to Stage 4 or the orchestrator — i.e., keep the function signature `(audio_segments) -> float` stable regardless of internal implementation.

---

## Stage 4 — AV Temporal Alignment (Cross-Modal)

**⚠️ BLOCKED until the Day 19 design session with Dev 2.** See `av-alignment-interface.md` — it is currently a blank placeholder. Do not implement this stage beyond a stub that accepts both inputs and returns a hardcoded score until that document is filled in.

**Purpose (for when it's unblocked):** Verify speech occurred at the same time the lips were moving — defeats replay-with-background-audio and TTS-injection-while-video-shows-a-real-person attacks.

**Design (from the project plan, subject to the Day 19 agreement on exact data shapes):**
1. For each spoken word's `[start, end]` window (from Stage 2's Whisper timestamps), find the corresponding video frames (using Dev 2's lip openness series + video fps).
2. Check what fraction of those frames show lip openness above a threshold.
3. Score = fraction of spoken-word windows with corresponding lip movement.
4. **Tolerance: ±300ms misalignment window** (human speech and lip movement naturally lag up to ~150ms).

Advisory only — low AV alignment alone never fails a session; it's complementary to, not redundant with, Stage 2's hard gate.

---

## Full Output Schema

```python
audio_result = {
  "score":  float,   # weighted combination of Stage 3 + Stage 4 scores
  "passed": bool,    # True ONLY IF Stage 1 AND Stage 2 hard gates both passed
  "reason": str,
  "error":  str | None,
  "details": {
    "speech_detected": bool,
    "speech_duration_seconds": float,
    "phrase_matched": bool,
    "digits_detected": list,
    "transcript": str,
    "voice_authenticity_score": float | None,
    "av_alignment_score": float | None   # None while Stage 4 is stubbed
  }
}
```

`details` is persisted to the eval store for debugging — it is not read by Dev 3's fusion engine, so it's safe to be generous with diagnostic content here.

---

## Latency Budget

Stages 1–3 combined: **< 10 seconds** (Stage 1 ~0.5s, Stage 2 ~4–6s, Stage 3 ~1s). If a stage blows this budget during implementation, run `/latency-benchmark` (see `.claude/commands/latency-benchmark.md`) before optimizing blindly.
