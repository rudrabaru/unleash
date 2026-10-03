# Audio Pipeline — Stage Specifications

Source of truth: Project Plan v2.1 Section 5. This document restates it in a form optimized for Claude Code to act on directly. If this document and the project plan ever disagree, treat that as a bug — flag it, don't silently pick one.

**Integration contract:** The audio module exposes one async entrypoint in `backend/app/modules/audio/__init__.py`: `process_audio_pipeline(media_path: str, challenge_phrase: str) -> DetectorResult`. Internally it runs Stages 1–4 in sequence and folds the result into a single `DetectorResult` (the 4-key contract, see root `CLAUDE.md` Section B). Dev 3's orchestrator calls only this one function — it does not call individual stages directly.

**Current implementation status:** Stages 1-4 are all `[REAL]` code. Stage 2 is a 5-word phrase gate (decisions D-01..D-04). Stage 4 is code-complete and consumes per-sample `time_seconds` (B4, implemented 2026-10-02 on the Stage 4 side); the producers (Dev 3 frame timing, Dev 2 lip series) do not emit it yet, so on real sessions it still degrades to `score=None`. Stage 4's interface was originally blocked on a Day 19 design session with Dev 2 that never happened; since Dev 2 was unavailable, Dev 1 wrote the agreed format solo (with explicit user authorization) — see `av-alignment-interface.md` for the finalized schema — and implemented the real alignment logic against it. Stage 4 remains advisory (`score` can be `None` when lip/word data is missing; `passed` is always `True`). The module is wired into `backend/app/orchestrator.py`, which extracts frame landmarks once and passes the lip openness series through.

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
- `speech_duration < 2.0 seconds` → `passed = False`, stop. Reason should say why (duration too short for a 5-word challenge).
- The `2.0` second threshold is a starting point, tunable in Phase 4 based on evaluation evidence — document any change here and in root `CLAUDE.md` if it affects gate behavior broadly.

**Output carried to later stages:** speech segments with start/end timestamps (seconds). Reused conceptually by Stage 4's tolerance window, though Stage 4 primarily uses Whisper's own word-level timestamps.

---

## Stage 2 — Phrase Compliance (STT + Matching)

**Purpose:** The core audio security control — verify the user said the server-issued 5-word challenge phrase.

**Tool:** `faster-whisper`, `base.en` model, int8, CPU (chosen by bake-off, decisions D-18/D-23; was `tiny`, which failed a genuine take). Plain transcription — **no vocabulary `initial_prompt`** (it makes Whisper emit vocabulary words on noise/tones). **Must be loaded once at process/module init, never per-request** (this is the #1 known gotcha — see `known-tricky-spots.md`). Always extract word-level timestamps; faster-whisper returns them natively — never discard them, Stage 4 needs them.

**Matching logic — do not use exact transcript matching:**
1. Take Whisper's word list with per-word probabilities. Lowercase each word and strip everything but letters (Whisper emits tokens like `Apple,`).
2. For each target word, pick the best-unused recognized word by edit-distance similarity, **normalised by 1× the longer word's length** (never 2× — that floored any two words at 0.5 and let ~90% of filler sentences pass).
3. A recognized word counts only if similarity ≥ `MIN_WORD_SIMILARITY` (0.8) **and** its Whisper probability ≥ the per-word confidence floor (`min_avg_confidence`, currently 0.5). Each spoken word can satisfy at most one target.
4. **Match threshold: at least 4 of 5 target words matched → `passed = True`.** 3 or fewer → `passed = False` (hard gate).
5. Exact string matching would produce unacceptable false-reject rates due to ASR noise/accents — a deliberate design decision, not a shortcut. Equally, do not loosen the similarity metric.
6. **Recognizer chosen (decisions D-18/D-23):** `base.en` plain, per-word confidence floor stays **0.5**. It passes the one real genuine take (4/5, no margin) that `tiny` failed (3/5: `Lenton`, `Nappal`), without lowering a gate threshold and without a vocabulary-hallucination channel. The vocabulary `initial_prompt` was rejected (noise → `zucchini` x6, tone → `beep` x13) and `hotwords` with the full vocabulary errors in faster-whisper 1.2.1. Evidence on a 60-clip synthetic TTS proxy (not human speech): `base.en` plain passes 51/60 at floor 0.5, 56/60 at 0.3, 58/60 at 0.2; the current `tiny` setup passed 32/60. **Still pending (D-04):** lowering the floor (candidate 0.3) needs >= 10 genuine human takes from >= 3 speakers; re-run `backend/prototypes/stage2_bakeoff.py` on them. Known gap: extra spoken words are not penalised (vocabulary-dump attack, see decision log open items).
7. **Pending (decision D-10, after a bake-off):** v1.1 may replace the fixed 5 rare words with 4–6 common words and word-level alignment scoring.

**Output:** full transcript, word-level timestamps (`{word, start, end, probability}` dicts), `phrase_matched: bool`, `match_count`, `matched_pairs`, `words_detected`, `target_words`.

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
`0.30/0.45/0.25` weights, the `0.1/0.2` buckets) is an initial guess
never fitted to a labelled recording set. Measured against the only labelled fixtures available
(2 genuine, 1 TTS), the composite shows **no separation** between genuine and TTS speech: 0.723 and
0.769 genuine vs 0.732 TTS. The spectral-flux term saturates to 1.0 on every real recording and the
HF-rolloff term runs opposite to its documented direction. **No value has been changed**, because
`test-scenarios.md` requires 8–10 recordings per scenario and we have 3 usable data points from 2
sources — see `docs/audio_pipeline_observations.md` §7 for the evidence and the recording set needed
to unblock calibration. Do not cite these numbers as tuned.

**Degraded-run honesty (changed 2026-10-02, decision D-15):** a sub-heuristic that cannot perform a real
measurement (librosa unavailable, audio shorter than one 512-sample STFT frame, no inter-speech
silence) now returns `None`, never a placeholder `0.5`. The composite is the weighted mean of the
heuristics that did measure (weights renormalised), and `details["degraded"] = true` with
`degraded_reasons` records which ones were excluded. If none measured, Stage 3 returns `score=None`
with an `error` and `passed=True` (advisory), and fusion drops it and redistributes its weight.

**Future upgrade path (v2, decision D-12 — evaluated offline first, adopted only if it separates genuine from TTS on our own recordings):** `speechbrain/aasist` (ASVspoof-trained). Pretrained spoof detectors generalise poorly to unseen TTS engines, so the evidence comes before the dependency. Design this stage's interface so swapping the heuristic for AASIST later requires no changes to Stage 4 or the orchestrator — i.e., keep the function signature `(audio_segments) -> float` stable regardless of internal implementation.

---

## Stage 4 — AV Temporal Alignment (Cross-Modal)

**Interface finalized** — see `av-alignment-interface.md` for the exact lip-series and word-timestamp shapes, written by Dev 1 solo (Dev 2 unavailable) with explicit user authorization, since the Day 19 session never happened.

**Purpose:** Verify speech occurred at the same time the lips were moving — defeats replay-with-background-audio and TTS-injection-while-video-shows-a-real-person attacks.

**Implementation (`_av_alignment.py`):**
1. For each spoken word's `[start, end]` window (from Stage 2's Whisper timestamps), widened by the ±300ms tolerance, collect the lip samples whose own `time_seconds` falls in that window. **No fps conversion**: browser `.webm` reports a bogus 1000 fps (B4/D-19), so the clock is the per-sample `time_seconds` the producers attach. Samples without a valid `time_seconds` are ignored; if none is valid the stage returns `score=None`.
2. Derive a per-session "open" threshold from the lip series' own median + half its stdev (lip geometry/camera distance vary per user, so a fixed global threshold doesn't generalize).
3. A word counts as aligned if ≥30% of its overlapping samples exceed that threshold.
4. Score = fraction of words (with ≥1 overlapping sample) that count as aligned.
5. **Tolerance: ±300ms misalignment window** (human speech and lip movement naturally lag up to ~150ms).

Degenerate inputs (no lip data, no word timestamps, or zero frame overlap for every word) return `score=None` with a `degraded_reason` in `details` — never a fabricated fraction (J5).

Advisory only — low AV alignment alone never fails a session; `passed` is always `True`. It's complementary to, not redundant with, Stage 2's hard gate. **Calibration status: `[UNCALIBRATED]`** — the 0.30 open-fraction threshold and the median+0.5*stdev "open" derivation are reasoned initial guesses, not fitted to labelled recordings, same honesty standard as Stage 3.

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
    "match_count": int,
    "words_detected": list,
    "target_words": list,
    "transcript": str,
    "voice_authenticity_score": float | None,
    "av_alignment_score": float | None   # None only when lip/word data is missing or non-overlapping
  }
}
```

`details` is persisted to the eval store for debugging — it is not read by Dev 3's fusion engine, so it's safe to be generous with diagnostic content here.

---

## Latency Budget

Stages 1–3 combined: **< 10 seconds** (Stage 1 ~0.5s, Stage 2 ~4–6s, Stage 3 ~1s). If a stage blows this budget during implementation, run `/latency-benchmark` (see `.claude/commands/latency-benchmark.md`) before optimizing blindly.
