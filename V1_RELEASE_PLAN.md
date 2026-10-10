# Unleash v1.0 - status and work order

Last updated 2026-10-10. Near-term plan; the long-term plan is `ROADMAP.md`. If they disagree: `.claude/context/decisions.md`, then `CLAUDE.md`, then these plans. Numbers below come from runs on the current code unless marked as a record from an earlier date.

## Scope

v1.0 is a **local live demo** of the read-speak-act challenge: every module runs on a browser recording, the must-pass checks fail closed, and results are reported as counts with their limits. It does **not** claim protection against deepfake, replay or synthetic voice (D-08). A hosted MVP (Docker, Railway, Vercel) follows the demo. Not in v1.0: smile, parallax, screen-flash (D-06, D-12).

The intended flow (one recording, 13 s): **Read** about 3 s (words shown, face the camera, nothing scored), **Speak** about 5 s (say the words, still shown), **Act** about 5 s (words disappear, a cue shows the head action: turn, hold, return to centre).

## Baseline, 2026-10-10 (package P0-E)

| Check | Result |
|---|---|
| Backend suite | 186 passed, 0 skipped in 102 s (the local deepfake checkpoint is present; a fresh clone skips the checkpoint tests) |
| Frontend | `npm run typecheck` and `npm run build` pass; the 5 screens render, no console errors; with no camera the pre-scan shows "No camera or microphone was detected" |
| Clip measurement (`tools/measure_clips.py`, 10 phone-style clips, **unflipped**; production flips, see P0-C) | analysis 5.9-9.7 s per clip |

| Clip | audio | liveness | challenge | deepfake | replay | verdict |
|---|---|---|---|---|---|---|
| BLINKING / TALKING / real / fake | fails (no phrase) | 0.93 | 1.00 | 0.50 / 0.50 / 0.48 / 0.48 | 0.42 / 0.30 / 0.30 / 0.30 | FAILED |
| DOWN / UP | fails | 0.84 / 0.83 | 1.00 | 0.46 / 0.46 | 0.30 / 0.30 | FAILED |
| TURN_LEFT / TURN_RIGHT | no audio track | 0.83 / 0.93 | 1.00 | 0.47 / 0.48 | 0.41 / 0.30 | FAILED |
| LIVELINESS_1 / _2 | fails / no audio | 0.49 | 0.00 (blink not seen) | 0.51 / 0.50 | 0.30 | FAILED |

**First full browser run (2026-10-10, Chromium with a fake camera and microphone, the real backend):** the five screens ran in order (get ready 3 s, Read, Speak, Act, analysing, result); the recording was VP8/Opus WebM from `MediaRecorder`; the server's windows lined up with the on-screen phases (no movement counted in Read or Speak). Both must-pass checks passed on the recorded file (head turn 46.9 deg held 0.88 s and returned; 4 of 5 words in order inside the Speak window, speech 4.0 s). The verdict was `SUSPICIOUS` 0.67: deepfake 0.49, replay 0.41 and lip sync 0 of 5 (the face and the voice in that test feed are different recordings) held it below `VERIFIED`, which is the interim-fusion problem (gate G2). The feed is the real turn-left sample flipped to an unmirrored picture plus the real spoken take, so it exercises the pipeline end to end but is not a recording of a person.

What it shows: **deepfake scores `real.webm` and `fake.webm` the same (0.48)**, so it does not separate them; **replay still scores genuine clips 0.30-0.42 against its 0.45 pass line** after the D-42 retune (the retune used genuine clips only); the joint veto no longer fires on these clips (deepfake is 0.46 or higher). Every verdict is `FAILED` because these clips do not contain the spoken phrase: this is a smoke check, not an accuracy figure. Peak memory was not re-measured (earlier record: 1.6 GB).

## Where things stand

| Area | Works | Open |
|---|---|---|
| Audio | ffmpeg extraction with truncation check; speech check; phrase check (`base.en`, 4 of 5, passes the one real take at 4/5); voice authenticity and lip sync run; temporary WAV always removed | Whole-clip, order not enforced, extra words free, 136 rare nouns hard to recognise, floor from one speaker; voice check and lip sync uncalibrated |
| Visual | MediaPipe landmarks, liveness, yaw/pitch challenge, lip series with real timestamps | No Read/Speak/Act windows, no hold, no return; blink challenge near-vacuous; liveness proves little; mirror handling inconsistent (P0-C) |
| Anti-spoofing | Deepfake (landmark crop) and replay run and report | Deepfake near chance (validation 33/56); replay design unsound; neither may decide anything |
| Fusion | Interim policy (D-51): must-pass checks fail closed; liveness and the challenge carry the score; deepfake, replay, voice and lip sync are report-only; minimum coverage caps at `SUSPICIOUS` | A genuine take reaches `VERIFIED`; the calibrated, learned fusion is gate G3 |
| Pipeline / API | One decode, one analysis entry, worker thread with lock, atomic claim, size cap, secret guard, orphan sweep | No duration/resolution caps before decoding; `ENVIRONMENT` defaults to development; no readiness endpoint; no rate limit |
| Frontend | 5-screen flow (D-45), builds and renders | Does not render phases from the server; developer strings in results; no MIME fallback |
| Evaluation | `tools/measure_clips.py`, `add_clips.py`, `phrase_model_comparison.py` | No attack recordings, no TAR/FAR tooling, `/scenario-runner` and `/threshold-sweep` cannot run |
| CI | Backend job, conflict-marker job, frontend type-check + build job (P0-B) | Not yet run on GitHub |

## Decisions already taken (2026-10-09)

Local demo first, then hosted MVP; desktop Chrome/Edge/Firefox only; three developers by work package (D-44); 5-screen frontend (D-45); the backend becomes phase-aware (windows, hold, return, ordered phrase in the Speak window); Act stays 5 s; both calibration approaches (challenge-bound statistical tests, then calibrated and learned fusion); the rare-noun vocabulary is replaced; only match counts and codes are stored (not the transcript); tracked sample clips stay with a consent note.

## Working rules

One package = one short-lived branch off `integration` and one pull request with green CI. `orchestrator.py`, `sessions.py`, `schemas/session.py`, `fusion.py`, `decisions.md` and `globals.css` have one writer at a time; P1-0 lands first. Every package that changes a check, threshold, weight, status value, contract or the upload design adds a decision-log line in the same commit and waits for the owner at its gate. Before recording the calibration set, freeze: phase windows, vocabulary, capture settings (audio constraints, bitrate, MIME type) and the yaw convention.

## Approval gates (the owner decides)

- **G1** (before P0-C, P1-0, P1-A, P1-B, P1-C): one signed yaw convention replaces the D-43 frame flip; challenge only in Act with hold at least 0.4 s, excursion at least max(15 deg yaw / 10 deg pitch, 5 sigma of the Read-window jitter), return to within max(8 / 6 deg, 3 sigma) of the baseline; phrase only in Speak, **ordered**, at least 4 target words in order and at most 3 inserted words; window guard 0.4 s (set from the pilot); `BLINK_TWICE` no longer issued (enum kept); `RETRY` status; additive `protocol` field in `POST /sessions`; minimum submit delay 12 s.
- **G2** (P1-D, P1-E, P1-J): interim fusion (deepfake, replay, voice authenticity and lip sync report-only, joint veto off, minimum coverage caps the verdict at `SUSPICIOUS`); transcript no longer stored; vocabulary pool and speech model; capture-constraint freeze.
- **G3** (after the campaign): learned fusion parameters, operating point and abstain band; each signal's entry decision; deepfake retrain or demote; screen-flash for v2.

Unchanged: the 4-key `DetectorResult` and the single-file upload.

## Work packages

**P0 - stabilise (days 1-2)**

| Pkg | Goal | Status |
|---|---|---|
| P0-A | Unbreak the frontend: modal half and its CSS removed, `next.config.mjs` environment-driven, `.gitignore` narrowed, `tsconfig.tsbuildinfo` untracked | done 2026-10-10 |
| P0-B | CI: frontend job, timeouts, model prefetch and cache key, pinned API dependencies, `pytest-timeout`, Dependabot | done 2026-10-10 |
| P0-C (G1) | One signed yaw convention; delete the `flip_horizontal` plumbing; browser-recorded left/right fixtures from two cameras asserted through the analysis; fix README and `challenge.ts` text | code, tests and docs done 2026-10-10 (D-46). **Open: record the browser fixtures** (a left turn and a right turn from each of two cameras with the recorder's "Save recording"), then add them under `backend/tests/fixtures/browser/` with a test per clip |
| P0-D | Four staged backend edits with tests; `.gitattributes`, D-44/D-45, working-mode text, consent note; both stashes dropped; stray plan file deleted | done 2026-10-10. The merged remote branches (`feature/deepfake-detection`, `liveliness-challenge`, `new-visual`) are left on GitHub on purpose |
| P0-E | Baseline above | done 2026-10-10 |

**P1 - local demo (about 1.5-2 weeks)**

| Pkg | Goal | Files |
|---|---|---|
| P1-0 (G1, done 2026-10-10) | Protocol plumbing, lands first: `app/protocol.py` (read 0-3, speak 3-8, act 8-13 s; min 12 s, max 16 s), additive `protocol` in the session response (schema, `types.ts` and the contract test together), `analyze_media(..., phases=None)` where `None` keeps today's behaviour | `protocol.py`, `schemas/session.py`, `sessions.py` (create), `orchestrator.py`, `types.ts` |
| P1-A (G1, done 2026-10-10) | Phased challenge in `visual/_pose_phased.py`: baseline from Read (0.5-2.7 s, median and robust sigma, at least 8 frames), action only in Act, hold, return, failure codes `no_motion`, `wrong_direction`, `no_hold`, `no_return` | `visual/_pose_phased.py`, `visual/__init__.py`, tests |
| P1-B (G1, done 2026-10-10) | Phased audio: WAV cropped to Speak (container 2.6-8.7 s), `audio/_phrase_align.py` ordered alignment, lip sync on Speak, deepfake/replay on frames before 8.7 s | `modules/audio/*`, tests |
| P1-C (G1, done 2026-10-10) | Validation and `RETRY`: `media/probe.py`, `app/quality.py`, checks before the session is claimed (reject over 30 s or 1920x1080; soft failures give `RETRY`) | `media/probe.py`, `quality.py`, `sessions.py` (`_check_submission`), schema |
| P1-D (G2, done 2026-10-10) | Interim fusion and stored data; rewrite `tests/test_fusion.py` so each test asserts its own intent | `fusion.py`, `db.py`, tests |
| P1-E (G2) | Vocabulary: frequency- and concreteness-filtered pool keeping the D-03 rules, generator kept; three-arm A/B (rare words, common words, template sentence) times `base.en`/`small.en`/`distil-small.en` | `vocabulary.py`, `tools/build_vocabulary.py`, `tools/phrase_model_comparison*.py` |
| P1-F (done 2026-10-10) | Frontend phases UI from `session.protocol`: pre-roll, timers, phase bar, beep and `aria-live`, hold-and-return cue, MIME fallback, `onerror`, poll retry | `frontend/src/app/*` except results |
| P1-G (done 2026-10-10) | Results, welcome and processing copy: reason-code to friendly message, `RETRY` screen, audio row shows pass state, debug toggle, true privacy text | `screens/Result.tsx`, `Welcome.tsx`, `Processing.tsx` |
| P1-H (done 2026-10-10) | Backend hardening: safe `ENVIRONMENT` default, `/verify` cap, streaming size cap, `/ready`, absolute paths, startup sweep | `config.py`, `main.py`, `db.py`, `verify.py` |
| P1-I (done 2026-10-10) | Tests: session API 401/404/real double-submit and a `VERIFIED` path, accidental-pass tests fixed, random-weights checkpoint-load test | `backend/tests/*` |
| P1-J (people) | Pilot of about 30 takes: sync-marker spike sets the guard, audio-constraint A/B, capture freeze | - |

**Local-demo gate:** a fresh clone installs and starts both servers; a genuine take from each of 3 speakers reaches `VERIFIED`; silence, wrong phrase, reordered phrase, 40-word reading, no turn, turn during Speak, wrong direction, turn without return and a photo do not; every failure shows a plain reason; the screen lists what is not calibrated.

**P2 - measure, calibrate, learn (about 2 weeks)**: P2-A manifest and trial plan; P2-B `tools/dump_features.py`, `tools/eval_report.py` (APCER/BPCER per attack, Clopper-Pearson intervals, leave-one-speaker-out); P2-C (G3) calibrators and learned fusion in `app/fusion_params/v1.json`; P2-D (G3) lip-sync permutation test; P2-E (people) campaign of about 300 takes (genuine: 3 speakers x 2 conditions x 4 actions x 3 repeats plus 30 no-action takes; attacks: phone replay 30, monitor replay 30, printed photo with live voice 30, TTS over a live face 30, speaker-replayed audio 15, wrong phrase, silence, wrong direction and no action 15 each); P2-F (G3) anti-spoof and voice decisions with data; P2-G `EVALUATION.md`.

A signal leaves report-only only if: leave-one-speaker-out AUC lower 95% bound is at least 0.70 against its target attacks; held-out log-loss improves in at least 2 of 3 folds; it is available on at least 90% of genuine takes; and its AUC lower bound is at least 0.60 in every device and lighting stratum. With zero accepts the 95% upper bound on the false-accept rate is 31% at n=8, 18% at n=15, 9.5% at n=30 and 4.9% at n=60: "FAR below 5%" needs about 60 attack takes per attack type, and three speakers are three clusters (final numbers need at least two held-out speakers).

**P3 - hosted MVP (about 2 weeks)**: P3-0 spike whether a 5 MB upload passes a Vercel rewrite (else call Railway directly); P3-A Docker, Railway, Vercel config; P3-B worker process with a kill timeout, bounded queue with position and ETA, `/ready`; P3-C rate limits, retention, security headers; P3-D Playwright end to end and structured logs; P3-E smoke and load test.

## Open items

- Phrase check floor (D-04) stays 0.5 until at least 10 genuine takes from at least 3 speakers exist.
- Deepfake: report-only until the retrain rule is met (validation at least 0.85 on 300 or more frames and genuine browser clips below 0.3 fake probability); checkpoint distribution (D-29).
- Hand gesture challenge, look up/down and the two-step head sequence: decide with the campaign data.
- Branch protection on `integration` and `main`: enforce by convention if the repository plan cannot.
- Frontend dependency: `npm audit` flags Next 14.2.35 (the last 14.x release; fixes need a major upgrade) and two transitive packages. The site is static pages plus a proxy, but the upgrade belongs to the hosting phase.
- `frontend/.env.local` on a developer machine may still hold the old `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1`; delete that line (the default is the same-origin proxy, see `.env.example`).
