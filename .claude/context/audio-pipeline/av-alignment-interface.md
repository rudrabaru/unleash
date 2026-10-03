# AV Alignment Interface Agreement — FINALIZED

**Status: agreed and implemented (the per-sample `time_seconds` clock, §5, is implemented on the Stage 4 side; the producers still have to emit it).** The original plan required a Day 19 design session
between Dev 1 and Dev 2 to settle this. That session never happened, and Dev 2 is not
available. Per explicit user authorization (see `implement-all-three-pillars.md`), Dev 1
wrote this agreement solo, based on the shapes the project plan had already specified plus
what the actual visual/audio code produces, and then built the real Stage 4 against it. If
Dev 2 later reviews this and wants changes, treat that as a new interface negotiation, not
a silent edit — update this file, `stage-specifications.md`, and root `CLAUDE.md` Section E
together in the same commit (per CLAUDE.md Section G/E).

## 1. Lip openness series (Dev 2's MediaPipe → Dev 1's Stage 4)

Produced by `backend/app/modules/visual/_lip_series.py::build_lip_series(features, fps)`,
where `features` comes from `backend/app/modules/visual/_landmarks.py::extract_landmark_features`.

```python
{
  "fps": 29.97,              # float — informational only; Stage 4 does NOT use it (see §5)
  "series": [
    {"frame_index": 0, "time_seconds": 0.00, "lip_openness_ratio": 0.041},
    {"frame_index": 1, "time_seconds": 0.51, "lip_openness_ratio": 0.038},
    # ... one entry per sampled frame where a face was detected (frames with no
    # detected face are omitted, not zero-filled)
    {"frame_index": 27, "time_seconds": 13.79, "lip_openness_ratio": 0.212},
  ]
}
```

- `lip_openness_ratio` = vertical distance between upper/lower inner lip landmarks (indices
  13/14), normalized by face height (forehead-to-chin, landmarks 10/152) — not raw pixel
  width, which was the standalone app's aspect-distortion bug. Unitless, typically in the
  ~0.02 (closed) to ~0.25+ (wide open) range, but not itself calibrated to an absolute
  "open" threshold — Stage 4 derives that per-session from the series' own baseline (see
  §3 below), since lip geometry and camera distance vary per user.
- `frame_index` is the index into the **same sampled frame list** produced by
  `app/modules/frame_extraction.py::extract_frames` (up to 30 frames, evenly subsampled
  across the full decoded clip) — not the original video's raw frame count. It is a label only:
  **never convert it to a time with `/ fps`** (browser `.webm` reports a bogus 1000 fps). The
  real clock is `time_seconds` (§4).
- An empty `series` (no frames had a detected face) is valid input, not an error — Stage 4
  must degrade to `score=None` in that case, never crash or fabricate a score.

## 2. Word timestamps (Dev 1's faster-whisper → Dev 1's own Stage 4)

Produced by `backend/app/modules/audio/_phrase_compliance.py::run_phrase_compliance`,
carried in its `DetectorResult.details["word_timestamps"]`.

```python
[
  {"word": "seven", "start": 1.02, "end": 1.34, "probability": 0.993},
  {"word": "four",  "start": 1.71, "end": 1.98, "probability": 0.981},
  {"word": "two",   "start": 2.15, "end": 2.40, "probability": 0.976},
]
```

Note this is a list of **dicts**, not the `(word, start_seconds, end_seconds)` tuples the
project plan sketched at a high level — faster-whisper's native word objects also carry a
per-word confidence (`probability`), which is worth keeping for diagnostics even though
Stage 4 itself only uses `word`, `start`, and `end`. `start`/`end` are seconds from the
start of the (ffmpeg-extracted, 16kHz mono) WAV, which shares a t=0 origin with the video
track since both come from the same single `.webm` blob (CLAUDE.md Section G: one file,
video+audio combined).

## 3. Tolerance window and alignment logic

±300ms misalignment allowance, as already agreed in the project plan Section 5.5 — not
renegotiated here.

For each word `{start, end}`:
1. Widen the window by the tolerance: `[start - 0.3, end + 0.3]`.
2. Collect all `lip_openness_ratio` values whose `time_seconds` falls inside
   `[window_start, window_end]` (no fps involved).
3. (Samples without a finite, non-negative `time_seconds` are ignored.)
4. A word's mouth movement is confirmed if the **fraction of those frames above the
   session's dynamic "open" threshold** is ≥ 0.30 (`WORD_OPEN_FRACTION_THRESHOLD` in
   `_av_alignment.py`).
5. The session's "open" threshold is derived from the lip series itself (not a fixed global
   constant, since lip geometry/camera distance differ per user):
   `open_threshold = median(series) + max(0.02, 0.5 * stdev(series))`.
6. Stage 4's score = fraction of words that pass step 4, across all words with at least one
   overlapping frame. Words with zero overlapping frames are excluded from both the
   numerator and denominator (not counted as failures) — a gap in frame sampling isn't
   evidence of a mismatch.

This is advisory only (10% weight in the system fusion, per CLAUDE.md Section D): it never
sets `passed=False`, regardless of the score.

## 4. Degenerate/missing-data behavior (still per J5 — never fabricate a score)

| Condition | Result |
|---|---|
| `lip_openness_data` is `None` or has an empty `series` | `score=None`, `passed=True`, `details["degraded_reason"]` set |
| `word_timestamps` is `None` or empty | `score=None`, `passed=True`, `details["degraded_reason"]` set |
| No sample carries a usable `time_seconds` (old `frame_index`-only shape, NaN, negative, non-numeric) | `score=None`, `passed=True`, `details["degraded_reason"]` mentions `time_seconds` |
| Every word has zero overlapping samples (e.g. all sampled frames landed elsewhere) | `score=None`, `passed=True`, `details["degraded_reason"]` set |
| Normal case | real fraction in `[0.0, 1.0]`, `passed=True` always |

---

## 5. Per-sample `time_seconds` (B4, decision log D-19)

**Status: IMPLEMENTED end to end (2026-10-02).** Consumer: Dev 1 (Stage 4). Producers: `visual/_frames.py` reads real PyAV presentation timestamps (decision D-19) for up to 120 frames, `extract_landmark_features` attaches them, `_lip_series.py` emits them, and `orchestrator.py` wires it. Verified on a face-less clip (timestamps equal the container's, frame for frame); a session with a detected face is still needed to see a non-null Stage 4 score.

**Problem (measured):** OpenCV reports MediaRecorder `.webm` as 1000 fps, and `frame_index` counts the 30 *subsampled* frames, not native frames. `frame_index / fps` therefore placed every lip sample near t = 0.03 s.

**Contract:** each lip-series entry carries a real timestamp:

```json
{"frame_index": 27, "time_seconds": 4.31, "lip_openness_ratio": 0.212}
```

- `time_seconds` = the frame's real presentation timestamp in seconds from the start of the clip (same t=0 as the audio), read with **PyAV** (D-19; fallback only if PyAV is unavailable: original frame index ÷ true fps, true fps = decoded frames ÷ ffprobe duration). Produced by `visual/_frames.py` and carried through `_lip_series.py` (Dev 2); a frame with no real timestamp gets no `time_seconds` field (never `frame_index / fps`). Must be finite and ≥ 0.
- `fps` stays in the series for reference only. Stage 4 matches word windows against `time_seconds` directly and ignores `fps`.
- **Stage 4 (Dev 1, done):** uses only entries with a valid `time_seconds`; if none are valid it returns `score=None` with a `degraded_reason` naming `time_seconds`. It deliberately does **not** fall back to `frame_index / fps`: with subsampled indices that gave plausible-looking but wrong scores (J5).
- Sampling density: Stage 4 works with any spacing (tests cover 30 frames over 15 s, ~10 fps, and variable frame rate). Denser sampling (B6) simply gives it more evidence per word.
- Tests: `backend/tests/test_stage4_av_alignment.py` (realistic 15 s clips, bogus 1000 fps, irregular timing, mismatch, invalid timestamps).
