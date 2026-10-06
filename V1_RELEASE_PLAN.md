# Unleash v1.0 - status and work order

Last updated 2026-10-05. Near-term plan; the long-term plan is `ROADMAP.md`. If they disagree: `.claude/context/decisions.md`, then `CLAUDE.md`, then these plans. Everything below is from code reads, test runs and probes on the current code, not from earlier reports.

## Scope

v1.0 is a **modular demo** (D-27): the audio, visual and anti-spoofing modules run on recorded input, every module returns the 4-key result, the must-pass checks fail closed, and results are reported as counts with their limits. No end-to-end human verdict (`VERIFIED` on a real person) is claimed, because no clip with a face *and* the matching phrase exists yet. The browser flow, the evaluation and deployment come after the detectors (D-38). Not in v1.0: smile, parallax, deployment (D-05, D-06).

## Where things stand

| Area | Works (measured) | Open |
|---|---|---|
| Audio checks | ffmpeg extraction with truncation check; speech check; phrase check (`base.en`, 4 of 5, passes the one real take at 4/5); voice authenticity and lip sync run; temporary WAV always removed. A genuine take through the whole pipeline passes in about 1 s warm. | Phrase check ignores word order and extra words. Floor needs human takes. Voice check and lip sync are uncalibrated; the lip-sync windows cover most of the speech span. |
| Visual | MediaPipe landmarks, liveness, yaw/pitch challenge (yaw sign verified on real clips), blink challenge, lip series with real timestamps. | The blink challenge cannot tell commanded from natural blinks. Liveness on one sample clip sits at the 0.5 line. |
| Anti-spoofing | Deepfake and replay run and return honest scores or errors. | **Deepfake checkpoint is near chance** (best validation accuracy 0.589; `fake.webm` 0.47 vs `real.webm` 0.48) and sees whole frames. **Replay scores every genuine clip 0.30-0.42 against a 0.60 line.** The checkpoint exists on one machine only. |
| Fusion | Weights, must-pass checks, joint veto, null redistribution; 17 tests. | `VERIFIED` is unreachable with the current deepfake and replay scores (score cap about 0.79); the joint veto fires on genuine UP and DOWN clips; no minimum signal coverage (see below). |
| Pipeline | One decode, one analysis entry (`analyze_media`), worker threads with a lock, atomic session claim, a development-only demo endpoint, a clip measurement tool. Warm analysis of a 5.5 s 1080p clip 12.8 s before the deepfake frame cap and 8-11 s per sample clip after; peak memory 1.6 GB. | Browser recordings (VP8/Opus, about 15 s) have not been measured. |
| Tests and CI | 155 tests green; a fresh clone runs 134 with one skip (no checkpoint). CI is one job (ffmpeg, conflict-marker check, full suite); not yet run on GitHub. | |
| Frontend | A recorder prototype (microphone only, shows the 5 words). | No camera, no upload, no result screen. |

Sample-clip measurement (10 clips, `python tools/measure_clips.py`; phone-style H.264 files, so a smoke check only): challenge passes on all 8 real-face clips performing it; liveness 0.47-0.93; deepfake 0.23-0.49; replay 0.30-0.42; every verdict `FAILED`.

## Open problems that block a genuine `VERIFIED`

1. **Deepfake and replay do not separate genuine from fake** and hold 35% of the weight (see above).
2. **No capture through the real path.** All real-face clips are phone-style files; the replay and clock results must be re-measured on browser recordings.
3. **No clip with a face and the matching phrase**, and no attack recordings (screen replay, photo, synthetic voice with face, wrong phrase, silence, wrong direction), so no false-accept rate exists.
4. **Fusion fails open:** with no minimum coverage, audio plus challenge alone can reach `VERIFIED` if liveness, deepfake and replay all error out.
5. **Phrase check:** order not enforced, extra words free, floor not chosen from human takes.
6. **Checkpoint not published** (SHA-256 in the README, URL missing).

## Work order (each step needs the owner's go-ahead; *decision* = changes what the system accepts, asked with a recommendation)

1. **Baseline table** with `tools/measure_clips.py` (done for the current code: above).
2. **Deepfake face crop:** take the face box from the dense landmarks, map it to the 30 native frames (landmark coordinates are normalised, so no second MediaPipe run), skip frames with no face, signal `None` if none. Re-measure.
3. **Recording slice of the browser flow:** extend the recorder page to camera plus microphone (about 720p, 30 fps), one VP8/Opus file, a "save clip" button.
4. **Record a calibration set through it (needs the owner):** genuine face and 5-word takes (eventually at least 10 from at least 3 speakers) and attacks: phone-screen replay, printed or on-screen photo, synthetic voice with face, wrong phrase, silence, wrong head direction (5-10 each).
5. **Detector decisions with data (*decision*):** deepfake retrain (same crop as runtime, split by source video, success = validation at least 0.85, genuine clips below 0.3 fake probability, `fake.webm` flagged, else reported but not scored); calibrate replay, voice authenticity and lip sync (lip sync needs a shuffled-audio control) and leave them unweighted until they separate; decide the joint veto, the weights and a minimum-coverage rule.
6. **Phrase check (*decision*):** enforce order and cap extra words; pick the floor from human takes.
7. **Prove the three pipelines work together:** one real face-and-phrase clip gives all five signals; the lip-sync control passes; the clock test stays green; the database round-trips; API schema matches the frontend types.
8. **Browser flow (5 screens)** from `docs/figma.zip`: 15 s auto-stop, submit, poll, result with per-signal breakdown; decide on an `/eval` page; automated end-to-end test with fake-media browser flags.
9. **Evaluation:** at least 8 recordings per scenario from at least 3 speakers, error rates per attack type, claims only from recorded results.
10. **v1.1 and deployment items** as listed in `ROADMAP.md`.

## v1.0 acceptance (module demo)

- Every module returns a valid 4-key result on every clip, including corrupt and empty input (tests).
- Must-pass checks fail closed with the right reason (silence, wrong phrase, wrong direction, no video, no audio).
- Request time under 20 s warm; speech plus phrase checks under 10 s.
- Known limits stated: deepfake near chance, replay and voice check and lip sync uncalibrated, sample is small, no genuine `VERIFIED` shown.
- Release steps: demo recorded from `/api/v1/verify`; one-page summary of the limits; `backend/unleash.db` and `temp_uploads/` cleared; pull request to `main` and a `v1.0.0` tag only if the owner decides to cut the release (D-13 is withdrawn).
