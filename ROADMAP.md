# Unleash — Long-Term Roadmap to the Final Deliverable

**Last updated:** 2026-10-02 · **Replaces:** the earlier "Verified Implementation Status & Next-Phase Team Plan" (its still-valid findings are folded into §2 and the appendix).
**Companion files:** `V1_RELEASE_PLAN.md` (the one-day v1.0, short-term) · `.claude/context/decisions.md` (decision log, in git) · `CLAUDE.md` §K (one-page summary).
**Authority order if files disagree:** `decisions.md` → `CLAUDE.md` → this roadmap / `V1_RELEASE_PLAN.md` → local `docs/` (which is gitignored and can drift).

---

## 1. The final deliverable — what "done" means

Unleash is a multimodal, active challenge-response **human-presence** verification system (not identity, not biometrics, not continuous monitoring). The **final deliverable** is an *evaluator-ready* package:

1. **A working, deployed system.** The 5-screen browser flow (landing → pre-scan → challenge → analysing → result) records camera + mic in one `.webm`, submits it, and shows a verdict (`VERIFIED` / `SUSPICIOUS` / `FAILED`) with a per-signal breakdown. FastAPI backend on Railway, Next.js frontend on Vercel, CPU-only, no LLM APIs.
2. **Hard gates proven on real recordings.** Visual challenge compliance, audio speech gate and audio phrase compliance each demonstrated, with recorded evidence, to stop the attacks they target.
3. **Measured accuracy, honestly reported.** TAR / FAR / FRR per attack species (ISO/IEC 30107-3 style APCER/BPCER) from a proper sample (8–10 recordings per scenario, ≥ 3 speakers), against the targets in CLAUDE.md §F. Latency under budget.
4. **Documented limits.** Which attacks are stopped, which are not, which signals are calibrated and which are not, in the technical summary and the demo.
5. **A repo a stranger can run.** README setup works on a clean machine, the deepfake checkpoint and test fixtures are obtainable, CI is green with fixtures, `main` is tagged.

**Claims policy (D-08):** "defends against X" is only written after X is measured. Until then the wording is "targets".

---

## 2. Where we are today (verified, 2026-10-02)

Everything below is from code reads, pytest runs and probe scripts — not from older reports.

| Area | Owner | Real today | Open |
|---|---|---|---|
| Audio Stages 1–4 | Dev 1 | ffmpeg extraction, silero-vad hard gate (≥ 2 s speech), faster-whisper tiny Stage 2 with a **fixed** matcher (4 of 5 words, similarity ≥ 0.8, case/punctuation stripped), librosa Stage 3 (advisory, uncalibrated), Stage 4 code complete. 4-key contract on every path. Unmeasurable sub-signals return `null`, not `0.5`. | **B10:** a genuine take failed Stage 2 (3/5) because Whisper tiny mishears isolated uncommon words; fix direction agreed (D-04), not yet coded. **B4:** Stage 4 gets no usable lip timing from browser `.webm` (1000 fps bug). 6 integration tests wait on new 5-word fixtures (B5). |
| Verbal challenge | Dev 1 / Dev 2 | 5 random words from a 136-word, phonetically-filtered vocabulary (CMU dict, no homophones), ≈ 35 bits. | `create_session` still uses `random`, not `secrets` (Dev 2). Rare nouns are hard for tiny (D-10 bake-off). |
| Visual | Dev 2 | MediaPipe landmarks, EAR liveness, yaw/pitch compliance (hard gate), BLINK_TWICE, lip series. | Yaw sign never verified on a real face (fixtures not committed). Only 30 frames per clip → blinks mostly missed (B6). LOOK_UP has no test. |
| Deepfake | Dev 3 | Self-trained Xception, CPU inference, real scores with the local checkpoint. | Checkpoint (250 MB) exists on one machine only (B7). Generalisation to modern face-swap is unproven. |
| Replay | Dev 3 | FFT moiré + temporal noise + brightness histogram; `[UNCALIBRATED]`; `null` when unmeasurable. | No replay recordings exist to calibrate it. |
| Fusion / orchestrator / SQLite / sessions API | Dev 3 | Weights, hard gates, joint veto, null redistribution, `av_alignment` fallback, HMAC tokens (120 s), single-use 409, temp-file cleanup, `GET /eval/sessions`. | No test reaches `VERIFIED`. |
| Frontend | Dev 2 / Dev 1 / Dev 3 | Day-8 audio prototype: mic permission handling, volume meter, 5-word display, local recording + download. Error banner (no fabricated sessions). | **No camera, no upload, no polling, no result screen, no `/eval` page.** Page requests `video:false`. A Figma design of all 5 screens exists in `docs/figma.zip`. |
| CI / infra | Dev 3 | pytest + audio import smoke test. | Skips fixture tests; never installs visual/antispoof requirements; no Dockerfile; `main` is still the initial commit. |
| Docs | all | CLAUDE.md, AGENTS.md, `.claude/context/*` synced to the 5-word design; decision log created. | `docs/` copies are local-only and amended, not shared. |

Test baseline: 81 passed, 6 known fixture failures (old "742" clips), 5 skipped (missing real-face `.mp4`), 1 expected xfail (Stage 3 vs TTS).

---

## 3. The roadmap at a glance

| Release | Theme | Size (estimate — team to confirm) | Exit gate |
|---|---|---|---|
| **v1.0** | **Make it work end to end, locally, honestly.** | 1 working day | Browser flow reaches a verdict; hard-gate attacks 0 reach `VERIFIED`/`SUSPICIOUS`; genuine 6/6 `VERIFIED`; CI green; `v1.0.0` tag. A demonstration, not a certified accuracy claim. |
| **v1.1** | **Make it measurable, harder to fool and deployable.** | ~1–2 weeks | Full evaluation meets §F targets; new challenge design in; public deployment passes the same smoke test. |
| **v2.0** | **Make it strong against what v1.x cannot stop.** | ~2–3 weeks after v1.1 | Screen-flash reflection and (if it earns its place) an audio spoof model adopted; final ISO-style report; evaluator package complete. |

Nothing starts on a red build. Every release crosses the same three gates: **Gate 0** build/tests green · **Gate 1** a real browser run reaches a verdict · **Gate 2** feature freeze (everything must-have merged, CI green, evaluation may begin).

---

## 4. v1.0 — local end-to-end demo (summary; full plan in `V1_RELEASE_PLAN.md`)

**Goal:** a genuine user on any of the three machines opens `localhost:3000`, is shown a visual action and 5 words, is recorded, and sees a verdict; the planned attacks end in `FAILED`.

**Must-have, by lane:**
- **Dev 1:** implement D-04/D-18 — choose the Stage 2 recognizer setup from the recorded probe (current best single-recording results: `base.en` plain = 4/5 at the *existing* 0.5 floor; `tiny.en` + vocabulary `initial_prompt` + `condition_on_previous_text=False` = 5/5 at floor 0.1) and confirm with ≥ 10 genuine takes, ≥ 3 speakers and the false-accept probes; record and commit the 5-word fixtures; make Stage 4 consume per-sample timestamps once B4 lands; run the audio part of the reduced evaluation.
- **Dev 2:** build the 5-screen flow from the Figma (camera+mic in one `.webm`, visual + verbal instruction, 15 s auto-stop, `POST /submit`, 2 s polling, result screen with per-signal breakdown); verify the yaw sign on real clips and add LOOK_UP; apply `secrets` in `create_session`; dense frame sampling for blinks with Dev 3.
- **Dev 3:** per-frame timestamps via **PyAV** (D-19) and dense visual sampling in `frame_extraction.py` (B4/B6); publish the checkpoint with SHA-256 (B7); add visual/antispoof requirements to CI; `/eval` page; an end-to-end test that reaches `VERIFIED`.
- **All:** 28-session reduced evaluation (6 genuine, 22 attack sessions across 8 scenarios), one CSV with an `attack_species` column; demo video; one-page summary naming the limits; release PR and `v1.0.0` tag.

**Explicitly not in v1.0:** smile, parallax, deployment, new gates (D-05, D-06).

---

## 5. v1.1 — measurable, harder to fool, deployable

v1.1 is where the project stops being a demo and becomes something an evaluator can trust. Seven workstreams; each names an owner lane and why it exists.

### A. Verbal challenge redesign (Dev 1) — decisions D-04, D-10
*Why:* the first real genuine speaker was rejected because Whisper tiny mishears isolated uncommon nouns (lantern, walnut, trumpet). Challenge **entropy** — not word vs digit — is what resists replay; recognizer accuracy is what decides false rejects.
1. **Finalise D-04.** Vocabulary `initial_prompt`, `condition_on_previous_text=False`, confidence floor chosen from probes (false-accept: filler, replayed phrase, noise-only, silence, 3-of-5; false-reject: ≥ 10 genuine takes, ≥ 3 speakers/accents/mics).
2. **Run the format bake-off** before changing anything else: the *same* recordings scored under (a) 6 digits, (b) 5 rare words (today), (c) 5 common high-frequency words, (d) a short template sentence. Metrics: genuine pass rate, false-accept rate, per-word error, latency. Pick the winner by evidence.
3. **If common words / sentence wins:** rebuild the vocabulary from high-frequency, phonetically distinct words (relax the 2-syllable rule where needed), generate phrases from a loose template ("adjective noun verb adjective noun"), and replace the fixed "4 of 5" count with **word-level alignment scoring** (WER-style: substitutions/insertions/deletions), keeping a hard pass line. Update Stage 2 spec, CLAUDE.md §D, tests and decision log in one commit (Section G).
4. **Keep it a hard gate**, same role as today.

### B. Visual challenge redesign (Dev 2) — decision D-09
*Why:* head turn is the best challenge (it changes 3D geometry, stresses face-swap models at large angles, is the most reliably measured). Blink is weak as a command; smile is easy for face-swap tools to render.
1. **Verify the existing five challenges on real face video** (yaw sign, pitch, BLINK_TWICE) — prerequisite for everything else.
2. **Two-step head-turn sequence** (e.g. left then up, random order/direction) instead of one action: raises attacker cost against a pre-recorded clip. Schema change to `VisualChallengeType`/session payload ⇒ Section G sign-off.
3. **Blink as a passive liveness signal**, not a challenge; dense frame sampling so it is actually measurable.
4. **Smile / mouth-open** and **parallax flatness** (non-affine landmark motion between landmark pairs at different depths during the turn) as **advisory** signals inside liveness `details`; no fusion-weight change.

### C. Cross-modal binding (Dev 1 + Dev 2 + Dev 3) — decision D-11
*Why:* the strongest differentiator we can build without new models — an attacker must fake voice **and** face movement together, in real time.
1. **Finish B4:** true fps and per-sample `time_seconds` through `frame_extraction.py` → `_lip_series.py` → Stage 4; update `av-alignment-interface.md` and CLAUDE.md §E together.
2. **Calibrate Stage 4** on real genuine and attack recordings (open threshold, ±300 ms tolerance).
3. **Speak while turning:** the user says the phrase *during* the head turn; check word timestamps against the yaw timeline. Advisory first; promote to a weighted signal only with evidence and sign-off.
4. **Late reveal and timing:** challenge shown only at recording start; log the delay before speech starts as an advisory signal.

### D. Abuse resistance and false-reject reduction (Dev 3 + Dev 2) — decision D-11
1. **Retry limits** per device/IP. With 5 visual actions an unlimited-retry attacker eventually gets a challenge a recorded clip matches.
2. **Capture-quality gate before analysis:** too dark, face too small/absent, mic clipped or silent, clip too short ⇒ a "try again" message that does not consume a session as `FAILED`. Cuts FRR, the weakest number today.
3. **Privacy hygiene:** confirm temp media is deleted after analysis; clear `temp_uploads/` and the demo DB before releases.

### E. Evaluation and calibration (all) — ISO/IEC 30107-3 style
1. **Full scenario sets:** audio 10 scenarios, visual 9, antispoof 8 — each 8–10 recordings, ≥ 3 speakers, ≥ 2 devices/mics, ≥ 2 lighting conditions. Real phone-screen and monitor replays, printed and on-screen photos, TTS clips from ≥ 2 engines (half played acoustically through a speaker).
2. **Report APCER/BPCER per attack species** (photo, screen replay, replayed phrase, TTS, face-swap if tooling exists), not one blended number; BPCER/FRR at fixed operating points.
3. **Threshold sweeps** with `/threshold-sweep` (Stage 1 duration, Stage 2 count/similarity/floor, EAR, yaw/pitch, fusion cut-offs); every change recorded with evidence.
4. **Calibrate** replay (FFT/noise/brightness weights and pass line) and Stage 3 against real attack recordings; mark them calibrated only afterwards.
5. **Honest TTS result.** A TTS voice reading the correct phrase passes Stages 1–2 by design; document what Stages 3/4 and the visual gate do with it.

### F. Delivery and infrastructure (Dev 3, with Dev 2 for the frontend)
1. **Backend Dockerfile** (ffmpeg, CPU torch, faster-whisper, silero-vad, MediaPipe, OpenCV, checkpoint fetch), **Railway** config with a persistent volume for SQLite; verify audio dependencies in a minimal deploy early (the original plan's "by Day 38, not Day 41" lesson).
2. **Vercel** config for the frontend; environment variable for the API base URL.
3. **Checkpoint and fixtures:** publish via a GitHub Release asset (or shared drive) with SHA-256 recorded; commit a small shared fixture set under `backend/tests/fixtures/`; stop relying on one machine's `.git/info/exclude`.
4. **CI:** install requirements-visual and requirements-antispoof, run fixture tests, fail on conflict markers (`git grep -nE '^(<<<<<<<|>>>>>>>)'`), protect `integration` and `main`, align branch names with CLAUDE.md §I.

### G. Technology stack upgrades (Dev 3 lead; Dev 1 / Dev 2 for their parts) — decisions D-17, D-20, D-21
*Why:* the core stack is sound (D-17), but a few gaps threaten reproducibility, deployment and the evaluation.
1. **Pin and lock** every runtime dependency (`mediapipe`, `timm`, `librosa`, `opencv`, `fastapi` still float); one Python version for CI and Docker (3.12 proposed — confirm wheels for all pins); split `requirements-dev.txt` out of the runtime file; Dependabot.
2. **CPU-only torch in Docker** from PyTorch's CPU index (plain `torch==2.9.1` on Linux normally pulls the CUDA build — huge, and against the no-GPU rule).
3. **Bake models into the image:** faster-whisper downloads from Hugging Face on first run (a runtime network call, plus a cold-start delay against the 120 s token). Pre-download Whisper at build time; silero-vad ships in its pip package; the MediaPipe model file is already committed.
4. **Playwright E2E with Chromium fake-media flags** feeding a recorded clip — automates the end-to-end test and makes the 28-session and full evaluations repeatable.
5. **Event-loop check:** confirm that analysis (sync Whisper/MediaPipe inside `async` functions) does not stall the 2 s polling; if it does, `asyncio.to_thread` (no Celery).
6. **Browser coverage:** test Chrome, Edge, Firefox and Safari; Safari records MP4. ffmpeg already decodes any container; the invariant to keep is *one combined video+audio file*, and CLAUDE.md §G's "single `.webm`" wording needs a team note before editing.
7. **SQLite WAL mode** on the Railway volume.

### H. Documentation (all)
Keep `decisions.md`, CLAUDE.md, `.claude/context/*` and this roadmap in sync in the same commit as any gate/threshold/schema change; refresh worklog and observations after each milestone.

**v1.1 exit gate:** full evaluation meets CLAUDE.md §F (TAR > 85%, FAR < 5%, FRR < 15%, Stage 2 accuracy > 90%, analysis latency < 20 s, Stages 1+2 < 10 s, end-to-end < 60 s) **or** the shortfall is documented with evidence and a plan; deployed system passes the same smoke test as local.

---

## 6. v2.0 — the final long-term deliverable

v2.0 adds the defences v1.x cannot provide and packages everything for an evaluator.

0. **Performance track (decision D-22), only with benchmarks:** export the Xception model to ONNX Runtime (smaller image, likely faster CPU inference, drops torch/timm from the runtime) and evaluate a closed-vocabulary recognizer (Vosk/Kaldi grammar limited to the challenge vocabulary) against Whisper on our recordings. Adopt either only if it wins on accuracy/latency on our data.
1. **Screen-flash reflection challenge** (decision D-12). Emit a randomized, session-unique colour/brightness sequence from the browser canvas; measure the face-ROI's reflected colour/luminance per frame; cross-correlate with the emitted sequence at the lag expected from camera latency (the "Face Flashing" / iProov-"Flashmark" family; ~97–99% reported on commodity webcams). A pre-recorded video cannot reflect a sequence it never saw, so this is the strongest candidate defence against replay and screen playback. **It changes the fusion signal set and needs a new capture protocol (flash timings + ground truth shipped with the `.webm`) ⇒ Section G team sign-off before any code.** Prototype advisory-only first; promote to a hard-gate candidate only with measured evidence.
2. **Audio spoof detection, evaluated offline** (decision D-12). Test a pretrained ASVspoof-family model (e.g. AASIST / RawNet2, CPU-feasible, non-biometric because it classifies spoofed vs genuine speech and stores no voiceprint) against *our* genuine and TTS recordings. Pretrained detectors generalise poorly to unseen TTS engines, so adopt only if it separates genuine from TTS on our data; keep Stage 3's function signature stable so the swap touches nothing else.
3. **Final evaluation and report:** repeat the full evaluation on the final build; ISO/IEC 30107-3-style APCER/BPCER by attack species; confidence statements that match the sample size.
4. **Evaluator package:** deployed URLs, demo video (genuine, replay, silent, wrong phrase, TTS), one-page technical summary listing known limits, README that works on a clean machine, tagged `v2.0.0`.
5. **Optional (only if time and evidence):** gaze-following on-screen dot (coarse precision, needs a calibration step).

**v2.0 exit gate:** the evaluator package in §1 is complete and every claim in it is backed by a recorded result.

---

## 7. Design rationale (why these choices)

### 7.1 Audio challenge format
| Format | Entropy | Recognizer accuracy | Notes |
|---|---|---|---|
| 3 digits | ≈ 10 bits | Best (tiny vocabulary) | Easy for TTS, low entropy; needs ≥ 6 digits to be safe |
| 5 random words (today) | ≈ 35 bits | Weak for rare nouns — "lantern"→"Lenton", "maple"→"Nappal" | Few lip-motion events for Stage 4 |
| Short template sentence | Comparable | Best for natural speech (language-model context) | Needs word-level alignment scoring |

Content never defeats TTS; randomness per session defeats replay, and timing/cross-modal binding (§5C) raises the cost of real-time synthesis. Format is chosen by the §5A bake-off, not by argument.

### 7.2 Visual challenge type
Head-turn sequence > smile > blink. Head turn changes 3D geometry (parallax), stresses face-swap models at large angles and is measured reliably by MediaPipe; its weakness is low entropy (4–5 actions), fixed by a random two-step sequence plus retry limits. Blink is performed unprompted in replays and is hard to sample at 30 frames — a passive signal only. Smile is cheap but face-swap tools render expressions easily — advisory variety only.

### 7.3 Technology choices (D-17)
| Component | Decision | Note |
|---|---|---|
| FastAPI + `BackgroundTasks`, SQLite, Next.js 14 | Keep | WAL mode on SQLite; check the event loop is not blocked by analysis |
| silero-vad, MediaPipe FaceLandmarker, ffmpeg subprocess | Keep | webrtcvad stays the pre-approved VAD fallback |
| faster-whisper | Keep the library; **choose the model/options by bake-off** (D-18) | `tiny`, `tiny.en`, `base.en`; `initial_prompt` vs `hotwords` (full 136-word `hotwords` errors in 1.2.1) |
| OpenCV | Keep for image ops | Frame **timing** moves to PyAV (D-19) |
| PyTorch + timm (Xception) | Keep; CPU-only wheels in Docker | ONNX Runtime export is a v2 candidate (D-22) |
| Railway + Vercel, GitHub Actions | Keep | Bake models in; cache pip; install visual + antispoof requirements in CI |
| Hosted LLM / inference APIs | Not used, not planned | CLAUDE.md §A |

### 7.4 What we deliberately do not build
- **rPPG (pulse from skin colour):** 15 s window, motion while speaking, and `.webm` chroma compression make it a noisy, often-null signal for real cost.
- **Lip-reading / silent-speech challenges:** true accuracy needs a trained visual-speech model, conflicting with the pre-trained/CPU-only constraint.
- **Reproducing FaceTec / AWS / Azure / ID R&D models:** closed, patented or cloud-dependent; only their *concepts* (parallax, reflection) are portable.
- **Identity or biometric matching, continuous monitoring:** out of scope by definition.

---

## 8. Threat model — what stops what (honest status)

| Attack | Signals that should stop it | Status today | Planned improvement |
|---|---|---|---|
| No speech / muted mic | Stage 1 hard gate | Works in tests | Quality gate gives "try again" (v1.1) |
| Wrong words / filler / background speech | Stage 2 hard gate | Works (filler 0%, replayed 0% in probes) | D-04 recognizer fix; common-word design (v1.1) |
| Replayed audio/video from another session | Random per-session 5-word challenge; Stage 2; visual challenge | Works for audio; visual challenge random but low entropy | Two-step sequence; retry limits (v1.1); screen-flash (v2) |
| Wrong head direction | Visual challenge hard gate | Code present; yaw sign **unverified** on a real face | Verify on real clips (v1.0) |
| Static photo / printout | Visual challenge + liveness (+ parallax) | Targeted; not measured | Parallax (v1.1), evaluation |
| Phone/monitor screen replay | Replay detector, deepfake, challenge | Replay uncalibrated; no recordings yet | Calibration (v1.1); screen-flash (v2) |
| TTS voice reading the phrase | Stage 3 (advisory), Stage 4 (lip sync), visual gate | **Not demonstrated to be stopped.** Stage 3 showed no genuine/TTS separation; Stage 4 dead on browser clips (B4) | B4 + calibration; speak-while-turning; offline spoof model (v2) |
| Real-time face-swap | Deepfake detector, challenge at pose extremes, AV alignment | Detector exists; generalisation unproven | Two-step turns, evaluation with real tooling, screen-flash (v2) |
| Bot brute-forcing challenges | HMAC tokens, 120 s expiry, single-use | Tokens enforced | Retry/rate limits (v1.1) |

---

## 9. Responsibilities by lane across releases

| Lane | v1.0 | v1.1 | v2.0 |
|---|---|---|---|
| **Dev 1 — audio** | D-04 fix; 5-word fixtures; Stage 4 timestamps; audio evaluation | Format bake-off; common-word design + word-level scoring; Stage 3/4 calibration; speak-while-turning (audio side); full audio evaluation | Offline spoof-model evaluation and swap-in |
| **Dev 2 — visual + screens** | 5-screen flow; yaw verification; `secrets`; dense sampling | Two-step sequence; passive blink; smile/parallax advisory; quality gate UI; Vercel | Screen-flash capture UI and timing |
| **Dev 3 — backend core + antispoof** | True fps/timestamps; checkpoint; CI; `/eval`; VERIFIED test | Retry limits; replay calibration; deepfake evaluation; Docker/Railway; branch protection | Screen-flash analysis; final report assembly |
| **All** | Reduced evaluation, demo, summary, tag | Full ISO-style evaluation; deployment smoke test | Evaluator package; `v2.0.0` |

Ownership rules from CLAUDE.md §C still apply: one developer's module folder is changed by another only by explicit agreement.

---

## 10. Critical path and dependencies

1. **D-04** (Stage 2 recognizer) → genuine fixtures that pass → Dev 3's `VERIFIED` test → Gate 2.
2. **Dev 3 true fps** → Dev 2 lip `time_seconds` → Dev 1 Stage 4 consumption (B4) → Stage 4 calibration → speak-while-turning.
3. **Real-face clips + yaw verification** → two-step sequence → any new visual challenge.
4. **Checkpoint distribution + CI requirements** → deepfake evaluation on every machine → full evaluation.
5. **Full evaluation data** → threshold sweeps → calibrated replay/Stage 3 → honest final claims.
6. **Section G sign-off** → screen-flash and any new hard gate or schema change.

---

## 11. Governance (how we avoid chaos)

- **Decision log:** every change to a hard gate, threshold, shared schema, fusion weight or scope is recorded in `.claude/context/decisions.md` in the same commit as the change (CLAUDE.md §G). Entries are never rewritten, only superseded.
- **Doc hierarchy:** `decisions.md` → `CLAUDE.md` → this roadmap and `V1_RELEASE_PLAN.md` → local `docs/`. Stale text is a bug: fix or flag it (the "3-digit / 2-of-3" text was exactly this).
- **Branches/PRs:** each developer on their own branch; small PRs into `integration` at each gate; nobody merges `integration` into a feature branch without pulling first; `main` only via reviewed PRs at release boundaries. Before every push: `git grep -nE '^(<<<<<<<|>>>>>>>)'` and the full pytest. A skipped test is not a passing test.
- **J5 (no fabricated values):** unmeasurable ⇒ `null` and excluded, never a placeholder score; stubs are labelled `[STUB]`; uncalibrated constants are labelled `[UNCALIBRATED]` until fitted to recorded evidence.
- **Definition of done for a stage/change:** 4-key contract holds on every path, hard gates fail closed, tests (including negative tests) added, evidence recorded, docs and decision log updated.

---

## 12. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Stage 2 still rejects genuine accents | FRR above 15%, TAR below target | D-04 probes with ≥ 3 speakers; format bake-off; word-level scoring |
| Yaw sign inverted on the visual hard gate | Genuine users fail or attacks pass | Verify on real clips first (v1.0); never add challenge types before |
| Deepfake checkpoint unavailable on other machines | Silent loss of a 20% signal | Release asset + SHA-256; CI check |
| Latency exceeds 20 s after dense frame sampling | Misses §F target | Dense sampling only for visual consumers; 30 frames for deepfake; benchmark |
| One-day v1 scope creep | v1 slips | Smile/parallax/deploy deferred (D-05/D-06); cut order in `V1_RELEASE_PLAN.md` |
| Over-claiming TTS/face-swap defence | Credibility loss | Claims policy (D-08); honest per-species report |
| Docs drift between machines | Conflicting instructions | Decision log in git; sync in the same commit |
| Hidden runtime model download / CUDA wheels in Docker | Slow or failing cold start, huge image, GPU dependency | Bake models into the image; CPU-only torch index (D-20) |
| Analysis blocks the server's event loop | Polling stalls during analysis | Event-loop check; `asyncio.to_thread` (D-21) |

---

## 13. Appendix — verified findings carried over from the earlier status report

- Fusion weights, hard gates, joint veto (`deepfake < 0.3 AND replay < 0.4`), score bands and null-redistribution match CLAUDE.md §D and are tested; SQLite is real (sessions / signal_scores / error_log); the orchestrator shares one frame + landmark pass and isolates each detector.
- Closed since that report: digit-homophone false-accept risk (replaced by the 5-word design); Stage 4 temp path now reads `settings.UPLOAD_TEMP_DIR`; `av_alignment` fusion fallback added with tests; liveness EAR-std dead code fixed (`d3e6b34`); merge conflicts resolved; Stage 2 matcher fixed; vocabulary regenerated; placeholder `0.5` scores removed; fabricated-session fallback removed.
- Still true from that report: the frontend has no camera, no `/submit` call, no polling/result screen and no `/eval` page; there is no Dockerfile or Vercel config; no test reaches `VERIFIED`; the project plan's "HuggingFace deepfake" wording is stale (amended locally and in CLAUDE.md).
- Research references behind §6–§7: Face Flashing (NDSS 2018) and iProov "Flashmark" (reflection challenge); FaceTec-style 3D/parallax liveness (concept only); ISO/IEC 30107-3 PAD testing methodology (APCER/BPCER by attack species); ASVspoof / AASIST (audio spoof detection); CMU Pronouncing Dictionary and PGP/EFF word lists (phonetically distinct vocabulary construction).
