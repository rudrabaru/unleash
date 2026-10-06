# Unleash - roadmap to the final deliverable

Last updated 2026-10-05. Near-term status and the current work order are in `V1_RELEASE_PLAN.md`; decisions in `.claude/context/decisions.md`. If files disagree: decision log, then `CLAUDE.md`, then the plans.

## 1. The final deliverable

An evaluator-ready package:

1. **A working, deployed system.** The 5-screen browser flow (landing, pre-scan, challenge, analysing, result) records camera and microphone into one file, submits it and shows `VERIFIED`, `SUSPICIOUS` or `FAILED` with a per-signal breakdown. FastAPI on Railway, Next.js on Vercel, CPU-only, no LLM APIs.
2. **Must-pass checks proven on real recordings:** the visual challenge, the audio speech check and the audio phrase check each shown, with recorded evidence, to stop the attacks they target.
3. **Measured accuracy, honestly reported:** TAR, FAR and FRR per attack type (ISO/IEC 30107-3 style APCER/BPCER) from at least 8 recordings per scenario and at least 3 speakers, against the targets in `CLAUDE.md`; latency under budget.
4. **Documented limits:** which attacks are stopped, which are not, which signals are calibrated.
5. **A repo a stranger can run:** one install command, the checkpoint and fixtures obtainable, CI green with fixtures, `main` tagged.

**Claims policy (D-08):** "defends against X" is written only after X is measured; until then the word is "targets".

## 2. Releases

| Release | Theme | Exit criteria |
|---|---|---|
| **v1.0** | A modular demo that is honest about its limits. | Every module returns a valid result on every clip; must-pass checks fail closed; request under 20 s; limits stated. No end-to-end human verdict claimed. |
| **v1.1** | Measurable, harder to fool, deployable. | The full evaluation meets the targets in `CLAUDE.md` (TAR above 85%, FAR below 5%, FRR below 15%, phrase accuracy above 90%, latency in budget) or the shortfall is documented with evidence; the public deployment passes the same smoke test as local. |
| **v2.0** | Strong against what v1.x cannot stop. | The screen-flash challenge and, if it earns its place, an audio spoof model; final ISO-style report, one-page summary, demo; every claim backed by a recorded result. |

Nothing starts on a red build. The current order of work is in `V1_RELEASE_PLAN.md`.

## 3. v1.1 workstreams

**A. Verbal challenge (D-04, D-10).** Run one recorded comparison of digits, rare words (today), common high-frequency words and a short template sentence on the same recordings, judged by genuine pass rate, false-accept rate, per-word error and latency. If common words or a sentence win: rebuild the pool from high-frequency, phonetically distinct words, generate phrases from a loose template, and replace the fixed 4-of-5 count with word-level alignment that also enforces order and caps extra words. Choose the confidence floor from at least 10 genuine takes from at least 3 speakers. It stays a must-pass check; update `audio-checks.md`, `CLAUDE.md`, the tests and the decision log in one commit.

**B. Visual challenge (D-09).** Run it as read, speak, act (words shown and said facing the camera, then the action) so the person can read and lip sync sees the mouth; test whether look up and down earn their place; evaluate a random hand-gesture challenge ("show N fingers") alongside the head actions. Head turn is primary: make it a random two-step sequence (raises the cost of a pre-recorded clip), make blink a passive liveness signal with dense sampling, add smile or mouth-open and a parallax flatness check as advisory signals. Adding challenge types changes `VisualChallengeType`, which needs approval.

**C. Cross-modal binding (D-11).** Calibrate the lip-sync check on real genuine and attack recordings with a shuffled-audio control; then have the person speak while turning and check word times against the yaw timeline (advisory first); show the challenge only at recording start and log the delay before speech.

**D. Abuse resistance and false rejects.** Retry limits per device or address (with 5 visual actions, unlimited retries let a recorded clip eventually match); a capture-quality check before analysis (too dark, face too small, microphone silent or clipped, clip too short gives "try again", not `FAILED`); privacy hygiene: delete temporary media after analysis (already done), minimise stored transcripts to the challenge words, restrict any evaluation view, a duration cap. Done (D-41): upload size cap, sweep of sessions stuck in `PROCESSING` at startup, refusal of the default `SECRET_KEY` outside development.

**E. Evaluation and calibration.** Full scenario sets recorded through the real browser path (at least two devices and two lighting conditions; real phone and monitor replays; printed and on-screen photos; synthetic voice from at least two engines, half played through a speaker). Report APCER and BPCER per attack type, not one blended number. Sweep thresholds with `/threshold-sweep`, recording each change with its evidence. Calibrate replay, the voice check and lip sync on real attack recordings and mark them calibrated only afterwards. Decide the deepfake model (retrain with the same crop as runtime, or report without scoring). Decide fusion fail-open and the joint veto with data (see the open items in the decision log).

**F. Delivery (D-20, D-21).** Backend Dockerfile (ffmpeg, libGL for OpenCV, CPU torch from the CPU index, models baked in, checkpoint fetched with its SHA-256); Railway with a volume for SQLite in WAL mode; Vercel with the API base URL as an environment variable; a published checkpoint or release asset; CI on every push; protect `integration` and `main`; Playwright end to end with Chromium fake-media flags; test Chrome, Edge, Firefox and Safari (Safari records MP4; the invariant is one combined video-and-audio file); model warm-up at startup so the first request is not slow; pin and lock dependencies with Dependabot.

## 4. v2.0

1. **Performance, only with benchmarks (D-22):** export the Xception model to ONNX Runtime; compare a closed-vocabulary recognizer (Vosk) against Whisper on our recordings. Adopt either only if it wins on accuracy or latency on our data.
2. **Screen-flash reflection challenge (D-12):** emit a random colour and brightness sequence from the browser canvas, measure the reflected luminance on the face per frame, and correlate it with the emitted sequence at the expected camera lag. A pre-recorded video cannot reflect a sequence it never saw. It changes the signal set and the capture protocol (flash times shipped with the recording), so it needs approval first; prototype as advisory, promote to a must-pass candidate only with measured evidence.
3. **Audio spoof detection, offline first (D-12):** test a pretrained ASVspoof-family model against our genuine and synthetic recordings; adopt it only if it separates them, keeping the voice check's function signature stable.
4. **Final evaluation and report:** repeat the full evaluation on the final build with confidence statements that match the sample size.
5. **Evaluator package:** deployed URLs, demo video (genuine, replay, silent, wrong phrase, synthetic voice), a one-page summary of the limits, a README that works on a clean machine, a `v2.0.0` tag.

## 5. Threat model: what stops what, today

| Attack | Signals that should stop it | Status | Planned |
|---|---|---|---|
| No speech or muted microphone | speech check | Stopped in tests | quality check gives "try again" (v1.1) |
| Wrong words, filler or background speech | phrase check | Stopped in tests (0% false accepts on 2,000 random challenges); order and extra words not enforced | word-level alignment (v1.1) |
| Replayed audio or video from another session | random phrase, phrase check, visual challenge | Audio stopped; visual challenge has only 5 random actions | two-step sequence, retry limits (v1.1); screen flash (v2) |
| Wrong head direction | visual challenge | Stopped on real clips (one performer) | two-step sequence |
| Static photo or printout | visual challenge, liveness | Targeted, not measured | parallax (v1.1), evaluation |
| Phone or monitor replay | replay detector, deepfake, challenge | **Not stopped**: replay scores genuine clips as fake and no replay recordings exist | calibration (v1.1); screen flash (v2) |
| Synthetic voice reading the phrase | voice check, lip sync, visual challenge | **Not demonstrated**: the voice check showed no separation; lip sync uncalibrated | calibration, speak-while-turning, offline spoof model |
| Real-time face-swap | deepfake, pose extremes, lip sync | **Not demonstrated**: the deepfake model is near chance | retrain or demote, two-step turns, screen flash |
| Scripted brute force | HMAC token (120 s), single use | Enforced; no retry limits | retry limits (v1.1) |

## 6. What is deliberately not built

Pulse from skin colour (a 15 s window with speech movement and compressed chroma gives a noisy signal for real cost); lip reading (needs a trained visual-speech model, against the CPU-only constraint); reproducing closed commercial liveness models (only their ideas, parallax and reflection, are portable); identity matching and continuous monitoring (out of scope by definition).

## 7. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| The phrase check rejects genuine accents | FRR above target | Floor from human takes across speakers; word-level alignment |
| Deepfake and replay stay near chance | `VERIFIED` stays unreachable | Retrain with the runtime crop, or report without scoring; calibrate on browser recordings |
| Calibration clips differ from browser recordings | Wrong thresholds | Record the calibration set through the browser recorder first |
| The checkpoint exists on one machine | The deepfake signal vanishes elsewhere | Publish it with its SHA-256; back it up |
| Over-claiming synthetic voice or face-swap defence | Credibility | Claims policy; per-attack-type report |
| Hidden model downloads or CUDA wheels in the image | Slow or failing cold start, huge image | Bake models in; CPU torch index |
| Latency after dense sampling | Misses the 20 s budget | Measured at 8-11 s per sample clip today; re-measure on browser clips |
