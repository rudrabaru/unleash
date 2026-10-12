# Unleash

> Read this file before changing anything. The decision log is `.claude/context/decisions.md` (read it before touching a must-pass check, a threshold, the contract or the scope). Plans: `V1_RELEASE_PLAN.md` (near term) and `ROADMAP.md` (to the final deliverable). If files disagree: decision log, then this file, then the plans.

## What Unleash is (and is not)

A multimodal, active challenge-response check that a live person is in front of a camera and microphone. A session issues a random visual action and a random 5-word phrase; the recording is checked for the action, the words, and signs of replay, deepfake or synthetic voice.

It **targets** replayed video, real-time face-swap, photos, scripted bots and synthetic audio. "Targets" is deliberate: nothing is called a defence until it is measured. Today the must-pass checks stop silence, wrong or replayed phrases, wrong head direction and photos in small-sample tests; synthetic voice and live face-swap are **not** shown to be stopped (the voice check and the replay detector are uncalibrated, and the deepfake model is near chance). Never claim otherwise without a recorded result.

It is **not** an identity or biometric system (no face or voice prints stored) and not continuous monitoring (one point-in-time session of about 15 s).

**Architecture:** one FastAPI backend (`backend/`) and one Next.js 14 frontend (`frontend/`); no microservices, no Celery. All inference is local and CPU-only (no LLM APIs, no GPU code). Models: silero-vad, faster-whisper `base.en`, MediaPipe FaceLandmarker, librosa, and a self-trained Xception deepfake classifier (trained offline, inference on CPU, checkpoint kept out of git). Models must be present locally; deployment (Docker, Railway, Vercel) is a later release.

## The detector result contract

Every detector returns exactly this (`backend/app/schemas/detector.py`, `DetectorResult`):

```json
{ "score": 0.92, "passed": true, "reason": "text", "error": null, "details": {} }
```

`score` is 0.0-1.0 (1.0 = genuine) or `null`; **when `error` is set, `score` is `null`**. `passed` is the module's own pass/fail. `reason` is never empty. `details` is diagnostic telemetry stored with the session; fusion reads only `details["voice_authenticity_score"]` and `details["av_alignment_score"]` from the audio result. A detector never raises: on any failure it returns `score=null, passed=false` with `error` set.

## Working mode: three developers, work packages (D-44)

Three people work in parallel on the whole project. There are no per-module owners and no ownership guard hook. The work is cut into packages with separate file sets (order and contents in `V1_RELEASE_PLAN.md`). One package is one short-lived branch off `integration` and one pull request that needs green CI before it merges. A few shared files (`orchestrator.py`, `sessions.py`, `schemas/session.py`, `fusion.py`, `decisions.md`, `globals.css`) have one writer at a time. Claude Code commits or pushes only when asked. The old ownership map is at git tag `pre-solo-reset` if a per-module split is ever wanted again.

## Signals, must-pass checks and fusion

| Signal | Technique | Role | Weight |
|---|---|---|---|
| Visual liveness | MediaPipe eye aspect ratio, blink, micro-movement | weighted | 20% |
| Visual challenge | MediaPipe head pose against the random action: turn, hold, return, in the Act window | **must pass** + weighted | 25% |
| Audio speech check | silero-vad, at least 2.0 s of speech inside the Speak window | **must pass** | - |
| Audio phrase check | faster-whisper `base.en`, Speak window; at least 4 of 5 words **in order**, similarity at least 0.8, word confidence at least 0.5, at most 3 extra words | **must pass** | - |
| Deepfake | self-trained Xception on CPU | report-only (uncalibrated, near chance) | 0 |
| Replay | OpenCV FFT moiré, temporal noise, brightness | report-only (uncalibrated) | 0 |
| Voice authenticity | librosa heuristics (uncalibrated) | report-only | 0 |
| Lip sync | word times against the lip series (uncalibrated) | report-only | 0 |

Only the visual challenge and the two audio checks are must-pass; a missing one fails closed. **Report-only** signals (D-51) run and are shown but add nothing to the score and cannot veto it, until a calibration campaign shows they separate genuine from attack (entry rule in `V1_RELEASE_PLAN.md`); there is no joint veto. **Verdict:** the weighted average of liveness and the challenge's score: `VERIFIED` at 0.80 or more, `SUSPICIOUS` 0.55-0.79, `FAILED` below 0.55 or any must-pass failure; if either weighted signal has no score the verdict is capped at `SUSPICIOUS`. `RETRY` (no score) means the recording could not be judged: too short, picture and sound out of step, no steady face at the start, a dead microphone, or an error on our side; it is neither an acceptance nor a failure. A signal with no score is excluded and its weight redistributed; it is never treated as 0. `VERIFIED` means "the challenge was done in this recording": it is **not** a claim of protection against deepfake, replay or synthetic-voice attacks. Known open problems with this scheme are in `V1_RELEASE_PLAN.md`.

## Module interfaces

- **Frames:** `app/media/frames.py::load_frames` decodes a recording once (PyAV) and returns up to 120 timestamped frames for the visual detectors and up to 30 native-resolution frames (a subset) for deepfake and replay, exactly as recorded (never mirrored: "left" is the person's own left in an unmirrored feed, see `visual/_pose.py`).
- **Lip series** (visual to lip sync): `{"fps": float, "series": [{"frame_index", "time_seconds", "lip_openness_ratio"}]}` on the container clock; **word times** (phrase check to lip sync): `[{"word", "start", "end", "probability"}]` relative to the extracted WAV. `process_audio_pipeline` converts one to the other's clock. Details: `.claude/context/audio-pipeline/av-alignment-interface.md`.
- **One analysis entry:** `app/orchestrator.py::analyze_media(path, visual_challenge, verbal_challenge)` runs every detector with failure isolation and returns signals, the fused verdict and per-step timings. The session flow (`run_verification`) and the development-only `POST /api/v1/verify` both use it. Detectors are plain blocking functions run in worker threads, one analysis at a time.

## Evaluation targets

TAR above 85%, FAR below 5%, FRR below 15%; phrase check accuracy above 90%; whole analysis under 20 s; speech plus phrase checks under 10 s; browser open to result under 60 s. Do not optimise one number while silently breaking a must-pass check or the contract. Rates from small samples are reported as counts, never as certified percentages.

## Needs the owner's explicit approval (and a decision-log line)

Changing the contract; which checks are must-pass or their thresholds; fusion weights, the joint veto or the verdict bands; the single-file upload design (one recording with video and audio, split server-side by ffmpeg); anything that needs a GPU at runtime. If a change like that seems necessary, stop and ask before writing code.

## Run it

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1                 # Windows PowerShell; macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt        # runtime + test tools; installs CPU-only torch
cp .env.example .env
uvicorn app.main:app --reload --port 8000  # health: /health, docs: /docs
python -m pytest tests -q                  # needs ffmpeg on PATH
python tools/measure_clips.py              # score every clip in eval/manifest.json
python tools/trial_plan.py                 # calibration checklist: clips recorded vs still missing
python tools/dump_features.py              # analyse eval/calibration.json once into eval/features.jsonl
python tools/eval_report.py                # counts, intervals and the per-signal rule from that file
```

Module demo (development only): `POST /api/v1/verify` in `/docs` with a recording, the visual action and the 5 words returns every detector's result, the verdict and timings. Frontend: `cd frontend && npm install && cp .env.example .env.local && npm run dev` (http://localhost:3000). Before any integration test, confirm the server answers `/health`.

The deepfake checkpoint is read from `backend/checkpoints/xception_deepfake_best.pth` (or `UNLEASH_XCEPTION_CHECKPOINT`); it is not in git and not yet published. Without it the deepfake signal reports an error and fusion excludes it.

## Rules in force

`.agents/rules/` (ask before assuming, no hardcoded stub values, the detector contract, repo hygiene, commit messages); slash commands in `.claude/commands/` (`/schema-check`, `/ready-check`, `/dead-code-audit`, `/solid-audit`, `/graceful-failure-audit`, `/latency-benchmark`, `/scenario-runner`, `/threshold-sweep`, `/commit-message`). Domain notes: `.claude/context/audio-pipeline/` (`audio-checks.md`, `av-alignment-interface.md`, `known-tricky-spots.md`, `test-scenarios.md`).

## Where the project is going

Release v1.0 is a modular demo (every module runs on recorded input; no end-to-end human verdict is claimed). v1.1 adds measurement, the common-word phrase, two-step head turns and deployment; v2.0 adds the screen-flash challenge, an offline-evaluated audio spoof model and the final report. Order of work and open decisions: `V1_RELEASE_PLAN.md`; every change to a check, threshold, schema or scope is logged in `.claude/context/decisions.md` in the same commit.
