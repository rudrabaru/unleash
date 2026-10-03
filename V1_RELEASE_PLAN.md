# Unleash v1 — Verified Status & One-Day Release Plan

Oct 1, 2026 · @Dhruv · **Updated Oct 2, 2026** after team sign-off (decisions D-04..D-16 in `.claude/context/decisions.md`)

> This is the **short-term** plan: the one-day v1.0 local demo. The long-term plan to the final deliverable is `ROADMAP.md`. If the two ever disagree, `.claude/context/decisions.md` decides, then `CLAUDE.md`.

## Status update — 2026-10-02

**What changed since the audit (Oct 1).**

| Item | Status | Notes |
| --- | --- | --- |
| B1 merge conflicts | **Done** | Backend imports, pytest collects. Dev 2 / Dev 3 still to review their own files. Import guards in `app/modules/__init__.py` stay removed for now (open decision). |
| B2 Stage 2 matcher | **Done** | 1× normalisation, similarity ≥ 0.8, case/punctuation stripped. Probe: filler 0%, replayed phrase 0%, genuine 100%. 5 regression tests. |
| B3 vocabulary | **Done** (Dev 2 still to apply `secrets.SystemRandom` in `create_session`) | 136 words, 25 letters, ≈ 35 bits, no homophones, 7 property tests. The earlier "roughly 200 words" target was not reachable under the phoneme and spelling constraints with the seed list; 136 words is enough for 35 bits. |
| Neutral `0.5` placeholders | **Done** | Replay and Stage 3 return `null` for unmeasurable sub-signals; weights renormalised. |
| Frontend verbal UI | **Done** | 5 words shown, "≥ 4 of 5 words" gate text, fabricated-session fallback removed, backend errors shown. Download Recording button added for local testing. |
| Docs sync (B8) | **Done in-repo** | CLAUDE.md, AGENTS.md, `.claude/context/*`, three audio reason strings; local `docs/` plan and guide amended; `ChallengePayload.verbal` description fixed. |
| **B10 (new): genuine speech fails Stage 2** | **Model fixed 2026-10-02 (D-23); confidence floor still open.** Stage 2 is now `base.en` plain, floor 0.5. The real take passes 4/5 (no margin); the vocabulary prompt was rejected because it makes Whisper emit vocabulary words on noise and tones. A floor change needs ≥ 10 human takes. | First real genuine take scored 3/5: Whisper tiny heard "Lenton" for "lantern" and "Nappal" for "maple". The `base` model did not help. A vocabulary `initial_prompt` fixes the transcript but lowers per-word confidence under the 0.5 floor. Fix direction agreed (D-04, widened by D-18). Extra probe on the same take: `base.en` plain = **4/5 at the existing 0.5 floor** (1.0 s); `tiny.en` + vocabulary prompt (`condition_on_previous_text=False`) = 5/5 at floor 0.1; `base.en` + prompt = 5/5 at floor 0.1 (1.7 s). One speaker, one recording — confirm before choosing. This is a TAR blocker for Gate 1. |
| B4 approach | **Decided** | PyAV per-frame timestamps (D-19). |
| B4, B5, B6, B7 | Open | Unchanged. B5 now also needs a genuine take that passes Stage 2. |

**Deviations from the long-term plan (so nothing is silent):**

1. **Local demo only.** No Dockerfile, Railway or Vercel in v1.0 (D-05). Deployment is v1.1.
2. **Reduced evaluation.** 28 sessions instead of 8–10 recordings per scenario (D-07). v1.0 is a demonstration with an honest small-sample report, **not** a certified TAR/FAR.
3. **Smile and parallax are out of v1.0** (D-06). The head-turn yaw sign has never been verified on a real face, so no new challenge type is added to that hard gate yet.
4. **Genuine-user bar is 6/6 `VERIFIED`** (D-07), not 5/6: 5/6 = 83%, below the plan's TAR > 85% target. A `SUSPICIOUS` genuine result is reported separately and does not count as a pass.
5. **Claims are "targets"** (D-08). v1.0 does not claim to stop TTS or real-time face-swap.

## Summary

*As audited on Oct 1:* the shared branch (`integration` = `feature/audio-pipeline` = commit `e81b0e1`) could not start the backend because a merge left conflict markers in four files (now fixed, see the status update above). With that fixed, the backend is a strong, well-tested core, while the frontend flow and evaluation have not been started.

**v1 for this release means:** a local, end-to-end browser demo (no public deploy) in which a genuine user reaches `VERIFIED` or `SUSPICIOUS`, and replay, silent and wrong-phrase attacks reach `FAILED`. It ships with a reduced but honest evaluation (28 sessions, reported as counts). The verbal challenge stays 5 random words, with the matcher, vocabulary and recognizer settings fixed. Smile, parallax and deployment are explicitly **not** in v1.0 (see `ROADMAP.md`, v1.1).

**Constraint:** one working day for three developers. The plan in this doc is therefore tiered into must, should and stretch work. Everything in *must* is required for a credible v1. *Should* items are attempted in order and moved to v1.1 if the day runs out.

**How this was verified:** every claim comes from reading the current code, running the backend suite with and without the local test fixtures, running `npm run build`, checking the GitHub Actions history, and running probe scripts against the real Stage 2 matcher and the real frame extractor. All remote branches (`new-visual`, `feature/deepfake-detection`, `liveliness-challenge`) are fully contained in `e81b0e1`.

## Current deliverable

The backend logic is largely real and tested. The two things a user actually touches, the browser flow and the measured accuracy, do not exist yet.

| Area | Owner | What is real today | What is broken or missing |
| --- | --- | --- | --- |
| Audio pipeline, Stages 1–4 | Dev 1 | ffmpeg extraction and truncation check, silero-vad speech gate, faster-whisper base.en transcription, librosa Stage 3, real Stage 4 code. The 4-key contract holds on every path. | Stage 2's 5-word matcher accepts almost anything (B2). Stage 4 never gets usable lip timing from browser recordings (B4). Six fixture tests fail (B5). |
| Verbal challenge | Dev 1 (vocabulary, matcher), Dev 2 (`create_session`) | 5 random words from `CHALLENGE_VOCABULARY`, HMAC-signed into the session token. | The vocabulary has 293 words, all starting with a or b. It includes exact homophones and was never actually run through the phonetic filter (B3). |
| Visual liveness and challenge | Dev 2 | MediaPipe FaceLandmarker (model file now committed), EAR, yaw/pitch from the transformation matrix, BLINK\_TWICE, lip series export. | Merge conflict markers (B1). Only 30 frames are sampled per clip, so blinks are mostly missed (B6). Real-face tests exist, but their `.mp4` fixtures are not in the repo. |
| Deepfake detector | Dev 3 | Self-trained Xception, CPU-forced, real non-null scores with the local checkpoint. | The 250 MB checkpoint is gitignored, and there is no way to give it to the other two machines or to CI (B7). |
| Replay detector | Dev 3 | FFT moiré, temporal noise and brightness histogram scoring, honestly marked `[UNCALIBRATED]`. | No replay recordings exist to calibrate it. |
| Fusion, orchestrator, SQLite, sessions API | Dev 3 | Weights, hard gates, joint veto, null-weight redistribution, `av_alignment` fallback (commit `bdce750`), shared landmark pass, HMAC tokens with 120 s expiry, single-use 409, temp-file cleanup, `GET /eval/sessions`. | The fusion tests are inside a conflicted file. No test reaches `VERIFIED`. |
| Frontend | Dev 2 (screens 1–5), Dev 1 (mic and verbal display), Dev 3 (`/eval`) | The Day-8 audio prototype: mic permission handling, volume meter, local recording. `npm run build` passes. A Figma Make design of all 5 screens is in `docs/figma.zip`. | No camera, no upload, no polling, no result screen, no `/eval` page. The verbal display still says "Read the 3-digit number". |
| CI and infrastructure | Dev 3 | GitHub Actions runs pytest and an audio import smoke test. | Red since `e81b0e1`. Never installs the visual or antispoof requirements. Skips every fixture test. No Dockerfile. `main` is still the initial commit. |

**Test baseline.** On `e81b0e1`, collection fails with 4 SyntaxErrors and 0 tests run. On the two parents of that merge, with the local fixtures copied in, the result is 65 passed, 6 failed, 1 xfailed and 5 skipped (`d3e6b34`). Without the fixtures it is 51 passed and 26 skipped, which is what CI and Dev 2 / Dev 3 see.

## Release blockers and new findings

Nine issues found in this audit are not in the previous plan. B1 to B4 would make any v1 demo either impossible or misleading.

| ID | Severity | Finding | Evidence | Fix |
| --- | --- | --- | --- | --- |
| B1 | Blocker | Unresolved merge conflict markers in `visual/_liveness.py`, `visual/__init__.py`, `tests/test_fusion.py` and `tests/test_visual_module.py`. The merge also removed the import guards in `app/modules/__init__.py`, so every `app.modules` import fails. | `python -c "import app.main"` raises SyntaxError. CI runs 36826458417 and 36828763307 both failed. | Take Dev 2's side (`d3e6b34`, the P0-4 EAR fix) in the two visual files. Take the union of both sides in the two test files. |
| B2 | Critical (hard gate) | The Stage 2 matcher divides edit distance by 2 × word length, so any two words score at least 0.5 against a 0.6 cut-off. | Probe over 2,000 random challenges: a generic 26-word sentence passes 90%. Replaying an old session's phrase passes 53%. 15,524 vocabulary pairs count as interchangeable. | Normalise by 1 × length, require similarity of at least 0.8 or edit distance of at most 1, keep the 4-of-5 rule, and add negative tests for both attack types. |
| B3 | High | `CHALLENGE_VOCABULARY` claims to be phonetically filtered but is not. | 293 words starting only with a or b. Exact homophones such as `by`/`buy` and `berry`/`bury`. Unsuitable words such as `bomb`, `bullet` and `breast`. Picked with `random`, not `secrets`. | Regenerate across a–z with a real phoneme-distance filter and a word blocklist. Use `secrets.SystemRandom` in `create_session`. |
| B4 | Critical (signal dead) | Stage 4 lip timing is wrong. OpenCV reports MediaRecorder `.webm` as 1000 fps, and `frame_index` counts the 30 subsampled frames, not native frames. | Every local `.webm` probed: 152 decoded frames, reported 1000 fps, and the last lip sample lands at 0.03 s. Stage 4 degrades to `None`, so its 10% weight is always redistributed. | Put a real timestamp on each lip sample (sample time = original index ÷ true fps, where true fps = decoded frames ÷ ffprobe duration). Update `av-alignment-interface.md` and CLAUDE.md §E together. |
| B5 | High | Six audio integration tests fail on the fixtures, because they feed the "742" digit recording against a 5-word challenge. CI never noticed, because the fixtures are excluded in Dev 1's local `.git/info/exclude`. | `test_pipeline_schema` (2 tests), `test_sessions_api`, `test_stage1`, `test_stage3` and `test_stage4` integration tests: "Only 0/5 words matched". | Record new 5-word fixtures and commit a small, shared `backend/tests/fixtures/` set. |
| B6 | High (hard gate) | `extract_frames` keeps 30 frames per clip. On a 15 s, 30 fps clip that is one frame every 0.5 s, while a blink lasts about 0.1–0.3 s. | BLINK\_TWICE is a hard-gate challenge, and liveness puts 40% of its score on blink detection. | Raise the sample count or sample densely for the visual consumers, and keep 30 frames for deepfake inference only. Check the latency budget after the change. |
| B7 | High (release) | The deepfake checkpoint and every test fixture exist on only one machine. CI never installs `requirements-visual.txt` or `requirements-antispoof.txt`. | `.gitignore` excludes `*.pth`, `*.webm`, `*.wav` and `*.mp4`. `ci.yml` installs only `requirements.txt` and `requirements-audio.txt`. | Share the checkpoint through a GitHub Release asset or a shared drive, with its SHA-256 recorded. Add the two requirement files to CI, which CLAUDE.md J3 explicitly allows. |
| B8 | Medium | Documents still describe the old 3-digit, 2-of-3 gate. CLAUDE.md Section G requires them to be updated together. | CLAUDE.md §D, `docs/unleash_project_plan.md`, `stage-specifications.md`, `test-scenarios.md`, `ChallengePayload.verbal` ("3-digit phrase"), and the audio reason text ("/3 challenge digits"). | One sync commit after B2 and B3 land. |
| B10 | High (hard gate, TAR) | A genuine speaker is rejected by Stage 2. | Real take, challenge `walnut lantern bicycle maple trumpet`: Stage 1 passed; Whisper tiny heard `Walnut, Lenton, Bicycle, Nappal, Trumpet` (3/5); latency 2.3 s. `base` also 3/5. With a vocabulary `initial_prompt` the transcript is right but per-word confidence (walnut 0.10, maple 0.23) falls under the 0.5 floor. | D-04: vocabulary hint, `condition_on_previous_text=False`, lower confidence floor (provisional 0.1; final value from probes: filler, replayed phrase, noise-only, silence, plus several genuine takes and speakers). Section G applies: the team agreed the direction; the value is recorded in the decision log. |
| B9 | Low | Housekeeping. | The deepfake docstrings still say no checkpoint ships. `backend/temp_uploads/` holds 31 leftover files (20 from real sessions), against the privacy NFR. Branch names differ from CLAUDE.md §I (`new-visual`, `feature/deepfake-detection`). | Clean up during the doc-sync commit. |

## Previous plan, item by item

Of the 23 items in the previous plan, 3 are done, 1 was replaced, 2 are partly done and 17 have not been started. Two of the done items are currently masked by B1.

| Item | Lane | Status | Evidence |
| --- | --- | --- | --- |
| P0-1 Digit homophones | Dev 1 | Replaced | Part 3A (5-word phrases) landed in `5ecca0e` and `41d22d4`. The digit map is gone, but the new matcher has the B2 defect. |
| P0-2 Stage 4 temp path | Dev 1 | Done | `audio/__init__.py` reads `settings.UPLOAD_TEMP_DIR`. |
| P0-3 `av_alignment` fusion fallback | Dev 3 | Done, tests masked | `fusion.py` fallback plus 4 new tests in `bdce750`. Those tests sit inside the B1 conflict block. |
| P0-4 Liveness EAR-std dead code | Dev 2 | Done, then lost | Fixed in `d3e6b34`. The `e81b0e1` merge left both versions between conflict markers. |
| P1-1 Real-face yaw-sign check | Dev 2 | Partly done | Tests for left, right, down and blink were written in `d3e6b34`. The `.mp4` fixtures are not in the repo, so the yaw sign cannot be verified here. LOOK\_UP has no test. |
| P2-1 Camera and audio in one `.webm` | Dev 2 | Not started | `page.tsx` still uses `video: false`. |
| P2-2 Screens 1–2 | Dev 2 | Not started | Only the `/` route exists. The Figma design exists. |
| P2-3 Screen 3: visual instruction, 15 s timer, submit | Dev 2 | Not started | No `/submit` call anywhere in `frontend/`. |
| P2-4 Screens 4–5: polling and result | Dev 2 | Not started | No code. |
| P2-5 Remove the mock-session fallback | Dev 2 | Not started | The fallback still fabricates a 3-digit challenge. |
| P2-6 `/eval` dashboard page | Dev 3 | Not started | The API exists, the page does not. |
| P3-1 Backend Dockerfile | Dev 3 | Not started | Out of v1 scope (local demo). |
| P3-2 Vercel config | Dev 2 | Not started | Out of v1 scope (local demo). |
| P4-1 E2E test that reaches `VERIFIED` | Dev 3 | Not started | Both lifecycle tests end in `FAILED`. |
| P4-2 Audio scenarios | Dev 1 | Not started | No recordings or CSV. `scenario_runner.py` exists locally. |
| P4-3 Visual scenarios | Dev 2 | Not started | — |
| P4-4 Antispoof scenarios | Dev 3 | Not started | — |
| P4-5 Results table, summary, demo video | All | Not started | — |
| Part 3A 5-word phrases | Dev 1 | Partly done | Live in code, with defects B2, B3, B5 and B8. |
| Part 3B Smile and parallax | Dev 2 | Not started | In v1 scope. |
| Part 3C ISO-style per-attack reporting | Dev 3 | Not started | Folds into the evaluation (`attack_species` column). |
| Part 3D Screen-flash challenge | — | Not started | Out of v1 scope. |
| H-1 Plan doc says "HuggingFace" deepfake | Dev 3 | Not started | `unleash_project_plan.md` lines 278 and 451 are unchanged. |

## Remaining tasks by developer

Every open item belongs to one developer's lane, following CLAUDE.md Section C. **\[M\]** = must ship for v1, **\[S\]** = should, **\[X\]** = stretch. Cross-boundary tasks name both sides.

### Dev 1 — Audio pipeline

- [x] **\[M\]** *(done 2026-10-02; Dev 2 / Dev 3 to review their files)* Resolve the B1 conflicts. Dev 1 ran the merge, so the fix starts here, with Dev 2 reviewing the visual files and Dev 3 reviewing `test_fusion.py`. Restore the `try/except` import guards in `app/modules/__init__.py`, or keep them removed by agreement.
- [x] **\[M\]** *(done 2026-10-02)* Fix the B2 matcher in `_phrase_compliance.py`: normalise by 1 × length, require similarity of at least 0.8 or edit distance of at most 1, and add negative tests (filler sentence, replayed old phrase, 3-of-5 correct).
- [x] **\[M\]** *(done 2026-10-02, 136 words)* Regenerate `CHALLENGE_VOCABULARY` (B3): a–z coverage, a real phoneme-distance filter, a blocklist, roughly 200 words. Hand Dev 2 a one-line `secrets.SystemRandom().sample(...)` change for `create_session`.
- [~] **\[M\]** **B10 / D-04 / D-18** — *model done 2026-10-02 (D-23): `base.en` plain, floor 0.5, no vocabulary prompt; CLAUDE.md and the stage spec updated; `backend/prototypes/stage2_bakeoff.py` is the repeatable probe.* **Still open:** record ≥ 10 genuine takes from ≥ 3 speakers (needs the humans), re-run the bake-off on them, and decide whether the floor drops to ~0.3 (Section G; record in `decisions.md`). The one real take now passes, so Gate 1 is no longer blocked by the recognizer.
- [~] **\[M\]** Record 5-word fixtures (B5) — *the 6 failing tests are green (2026-10-02): they use `backend/tests/fixtures/genuine_5word.webm` (the real audio-only take) and a composite `genuine_5word_noface_video.webm` (same audio on a face-less video track) via `tests/_audio_fixtures.py`.* **Still open:** 2 face-visible genuine clips, a wrong-phrase clip and a silent clip recorded through the browser, and committing the set (`*.webm` is gitignored, so it needs an exception and the speaker's OK).
- [x] **\[M\]** *(done 2026-10-02)* Update the verbal-challenge UI: show 5 words, "Read these 5 words aloud", "Gate: 4 of 5 words", and drop the digit fallback.
- [ ] **\[M\]** Make Stage 4 consume per-sample timestamps once Dev 2 and Dev 3 provide them (B4), and add a test with realistic timings.
- [ ] **\[S\]** Run a reduced audio evaluation (P4-2), described in the release checklist.
- [x] **\[M\]** *(done 2026-10-02 for in-repo files)* B8 documentation sync (CLAUDE.md, AGENTS.md, `.claude/context/*`, `ChallengePayload` description, reason strings). Update again when D-04 and B4 land.
- [ ] **\[X\]** Use `/threshold-sweep` on the evaluation recordings to justify the 4-of-5 rule and the final confidence floor.

### Dev 2 — Visual pipeline and user-facing screens

- [ ] **\[M\]** Review the B1 resolution of `_liveness.py` and `visual/__init__.py`, and confirm the P0-4 EAR-std fix is intact.
- [ ] **\[M\]** Commit the real-face fixtures (`left`, `right`, `down`, `blink`) plus a new `up` clip, confirm the yaw sign, and add the missing LOOK\_UP test (P1-1).
- [x] **\[M\]** *(done 2026-10-02, D-25: PyAV timestamps, 120 dense frames wired through the orchestrator; needs Dev 2 / Dev 3 review and a real-face session)* With Dev 3, sample frames densely enough for blinks (B6). Add a time in seconds to each lip-series entry (B4).
- [ ] **\[M\]** Build the 5-screen flow from the Figma design (P2-1 to P2-5): one camera-and-mic `.webm`, the visual and verbal instructions, a 15 s auto-stop, `POST /submit`, polling every 2 s, the result screen with per-signal breakdown, and no mock-session fallback.
- [x] **\[M\]** *(done 2026-10-02, D-25)* Apply the `secrets` change in `create_session` (B3).
- [ ] **\[v1.1\]** *(moved out of v1.0, D-06)* Smile / mouth-open challenge — adds a `VisualChallengeType` value in the shared `schemas/` (Section G).
- [ ] **\[S\]** Run a reduced visual evaluation (P4-3).
- [ ] **\[v1.1\]** *(moved out of v1.0, D-06)* Parallax flatness check as an advisory sub-signal inside liveness `details`, without changing fusion weights.

### Dev 3 — Anti-spoofing, backend core and infrastructure

- [ ] **\[M\]** Review the `test_fusion.py` union so all 4 `av_alignment` tests run and pass.
- [ ] **\[M\]** Fix B7: publish the checkpoint with its SHA-256 and a fetch step in the README. Add `requirements-visual.txt` and `requirements-antispoof.txt` to `ci.yml` and the README setup. Point CI at the committed fixtures.
- [ ] **\[M\]** In `frame_extraction.py`, read real per-frame timestamps with **PyAV** (`av`, already installed via faster-whisper — decision D-19) instead of OpenCV's bogus 1000 fps / "frames ÷ ffprobe duration", return `time_seconds` per sampled frame, and sample densely for the visual consumers while keeping ~30 frames for deepfake inference (B4/B6, with Dev 2).
- [ ] **\[M\]** Build the `/eval` page against `GET /eval/sessions` (P2-6).
- [ ] **\[M\]** Add an end-to-end test that reaches `VERIFIED` or `SUSPICIOUS`, using Dev 1's genuine fixture (P4-1).
- [ ] **\[S\]** Run a reduced antispoof evaluation (P4-4) and add the `attack_species` breakdown (Part 3C).
- [ ] **\[S\]** Fix the H-1 project-plan wording and the stale deepfake docstrings (B9).
- [ ] **\[M\]** *(promoted from stretch, D-13)* Open the release PR from `integration` to `main` and tag `v1.0.0` after Gate 2 and the evaluation.

## One-day v1 plan

The day runs through three gates. Nothing starts on top of a red build, and the code freezes before any evaluation recording starts.

&#91;embedded content: one-day v1 plan · 3 lanes, 3 gates\]

Read it top to bottom: each lane works in parallel inside a band, and nobody crosses a gate line until the whole team has met it.

1. **Gate 0, build green (first hour).** B1 is resolved and reviewed, `pytest` collects and passes with the fixtures, and `/health` responds. Every other task waits for this.
2. **Gate 1, first real end-to-end run.** A browser recording (camera and mic) is submitted, analysed, and shows a verdict on the result screen. This needs Dev 2's screens 1–3, Dev 1's matcher, vocabulary and fixtures, and Dev 3's frame timing.
3. **Gate 2, feature freeze.** All \[M\] items are merged into `integration`, the suite is green in CI, and the `VERIFIED` end-to-end test passes. After this point, only evaluation runs, write-ups and release steps happen.

**Dependency order:**

- Dev 1's genuine 5-word fixture unblocks Dev 3's `VERIFIED` test, so record it early.
- Dev 3's frame timing unblocks Dev 2's lip timestamps, which unblock Dev 1's Stage 4 change.
- D-04 (Stage 2 recognizer settings) must land before Dev 1's genuine fixtures are recorded and before Dev 3's `VERIFIED` test, otherwise the genuine fixture itself fails Stage 2.

**Merge protocol for the day:**

- Each developer stays on their own branch and opens a small PR into `integration` at each gate. One person merges, and everyone pulls straight after.
- Before every push, run `git grep -nE '^(<<<<<<<|>>>>>>>)'` and the full `pytest`.
- Never commit with fixtures missing locally. A skipped test is not a passing test.

**If the day runs short, cut in this order:**

1. The per-species evaluation breakdown (report plain counts per scenario instead).
2. The \[S\] reduced visual and antispoof evaluations (never the audio-gate or hard-gate attack sessions).

Smile and parallax are no longer in this list: they are v1.1 (D-06). Never cut a Gate 0 or Gate 2 item, the D-04 fix, or the `v1.0.0` tag.

## v1 test and release checklist

v1 ships when every hard-gate attack in the reduced evaluation ends in `FAILED`, and genuine users clear the bar below. Every number is reported as a count (for example 6/6), not as a percentage, because the sample is small. v1.0 is a demonstration with an honest small-sample report; it does **not** certify a TAR or FAR (D-07).

### Reduced evaluation protocol

All sessions run through the real browser UI after Gate 2. Each one is logged to one shared CSV with these columns: session ID, scenario, `attack_species`, speaker, expected verdict, actual verdict, and the five signal scores (copied from `/eval`). This is a one-day sample. The plan's 8–10 recordings per scenario stay in the post-v1 backlog.

| Scenario | Attack species | Sessions | Expected | Gate exercised |
| --- | --- | --- | --- | --- |
| Genuine user, correct phrase and action | none | 6 (2 per developer) | `VERIFIED` (`SUSPICIOUS` counted separately) | all |
| Silent (mic muted) | silence | 3 | `FAILED` | Stage 1 |
| Wrong 5-word phrase | wrong phrase | 3 | `FAILED` | Stage 2 |
| Phrase from an old session, or filler speech | replayed phrase | 3 | `FAILED` | Stage 2 (B2 regression) |
| Wrong head direction | non-compliance | 3 | `FAILED` | Visual challenge |
| Printed or on-screen static photo | photo | 3 | `FAILED` | Visual challenge, liveness |
| Phone-screen video replay | screen replay | 3 | `FAILED` | Challenge, replay, deepfake |
| TTS clip of the correct phrase | TTS | 2 | Document honestly | Stage 3 (advisory) |
| Background podcast, user silent | ambient speech | 2 | `FAILED` | Stage 2 |

### Acceptance criteria

| Criterion | v1 target | Source |
| --- | --- | --- |
| End-to-end browser flow on localhost | Works for all 3 developers' machines | Plan §13 |
| Hard-gate attacks (silent, wrong phrase, replayed phrase, wrong direction, photo) | 0 reach `VERIFIED` or `SUSPICIOUS` | Plan §13 |
| Genuine users | **6/6** `VERIFIED` (agreed, D-07). A `SUSPICIOUS` is reported separately and is not a pass. 5/6 = 83% would be below the plan's TAR > 85%. | Plan §11 TAR > 85% |
| Phone-screen replay | 0/3 `VERIFIED` | Plan §13 |
| Analysis latency, submit to result | Under 20 s on each session | Plan §10 |
| AV alignment | Non-null score on genuine sessions | Plan §13 |
| `/eval` shows per-session signal breakdown | Required | Plan §13 |
| CI on `integration` | Green, with fixtures and all requirement files | B1, B7 |

### Release steps

- [ ] Gate 2 passed and CI green on `integration`.
- [ ] Evaluation CSV complete, with results table and per-species counts written up.
- [ ] Demo video recorded: genuine user, replay attack, silent attack, wrong phrase.
- [ ] One-page technical summary that names the known limits (Stage 3 and replay are uncalibrated, and the sample is small).
- [ ] PR from `integration` to `main` reviewed by all three, merged, and tagged `v1.0.0`.
- [ ] `backend/temp_uploads/` and `unleash.db` cleared before the demo.

## Post-v1 polish backlog

These items are deliberately out of the one-day scope. They are listed in the order they would most improve trust in the verdict.

| Item | Lane | Why it matters |
| --- | --- | --- |
| Full evaluation: 8–10 recordings per scenario, at least 3 speakers, ISO/IEC 30107-3-style APCER/BPCER by attack species | All | v1 counts are too small to state a TAR or FAR with confidence |
| Calibrate the replay detector and Stage 3 against real attack recordings | Dev 3, Dev 1 | Both are scored today but marked uncalibrated |
| Tune thresholds with `/threshold-sweep` (Stage 1 duration, Stage 2 4-of-5 and confidence floor, EAR, yaw/pitch) | Dev 1, Dev 2 | Every threshold change needs recorded evidence, per the plan |
| Smile / mouth-open challenge and parallax flatness check | Dev 2 | Moved out of v1.0 (D-06); v1.1 advisory signals |
| Common-word phrase + word-level alignment scoring (after a digits / rare words / common words / sentence bake-off) | Dev 1 | D-10: Whisper tiny is weakest on isolated uncommon nouns |
| Two-step head-turn sequence; speak-while-turning binding; capture-quality gate; per-device retry limits | Dev 2, Dev 1, Dev 3 | D-09, D-11: raises attacker cost and cuts false rejects |
| Stack hardening: pinned deps + lockfile, one Python version, CPU-only torch, models baked into the image, `requirements-dev.txt`, Playwright E2E, event-loop check, Safari/MP4 coverage, SQLite WAL (D-20, D-21) | Dev 3 (+ Dev 2 for browsers) | Reproducible, deployable, repeatable evaluation |
| ONNX export of the Xception model; closed-vocabulary recognizer (Vosk) as a bake-off candidate (D-22) | Dev 3, Dev 1 | Evaluate before adopting |
| Any other \[S\] item not finished today (per-species breakdown, reduced evals) | Dev 2, Dev 3 | Planned v1 scope that may slip |
| Public deployment: `backend/Dockerfile` (ffmpeg, CPU torch, checkpoint), Railway volume for SQLite, Vercel frontend | Dev 3, Dev 2 | v1 is local-only by decision |
| Screen-flash reflection challenge (Part 3D) | Team decision | First new hard-gate candidate (D-12); needs Section G sign-off and a new capture protocol |
| Pretrained audio spoof detector, evaluated offline | Dev 1 | D-12: adopt only if it separates genuine from TTS on our recordings |
| Gaze-following dot challenge | Dev 2 | Coarse precision and needs a calibration step |
| Align branch names with CLAUDE.md §I and protect `integration` and `main` with required CI | Dev 3 | Would have stopped B1 from landing |

## Open decisions for the team

**Resolved (2026-10-02):** who resolves B1 (Dev 1, done; Dev 2 / Dev 3 review their own files); Stage 2 keeps 4-of-5 with the stricter per-word match (D-02); the genuine-user bar is 6/6 (D-07); smile is deferred to v1.1 (D-06); v1 is local-only (D-05); `v1.0.0` is a must (D-13).

**Still open:**

- [ ] **Stage 2 confidence floor** (D-04): the recognizer is `base.en` plain (D-23). Decide whether the floor stays 0.5 or drops (candidate 0.3) from ≥ 10 genuine takes and ≥ 3 speakers.
- [ ] **Vocabulary-dump attack (found 2026-10-02):** extra spoken words are not penalised; reading about 40 vocabulary words covers a challenge ≈ 2.6% of the time. A word-count cap would be a hard-gate change (Section G).
- [ ] **Lip-series interface change (B4):** add per-sample `time_seconds` to the lip openness series. This updates CLAUDE.md §E (row already added as *pending*) and `av-alignment-interface.md` in the same commit.
- [ ] **Keep or drop the import guards** in `app/modules/__init__.py`? `d3e6b34` added them and the merge removed them. Currently removed.
- [ ] **Do Dev 2's real-face clips exist?** Can they be committed, and did the left/right yaw tests pass on Dev 2's machine? (Needed to verify the yaw sign of a hard gate.)
- [ ] **Checkpoint distribution (B7):** where the 250 MB Xception checkpoint is published and who records its SHA-256.
