# Unleash — Shared Team Intelligence

> Read this file before doing anything else in this repository. It applies to all three developers.
> Companion documents (project scope, not checked into git): the project plan, team companion guide, and pipeline visualization doc live in `docs/` locally on each developer's machine (that folder is gitignored — private working docs, not shared history).
> Dev 1's deep audio-pipeline spec lives in `.claude/context/audio-pipeline/` (see Section E). Dev 2 and Dev 3 will add equivalent folders for their verticals when they set up their own Claude Code workflow. (Note: this lives under `.claude/context/`, not `.claude/agents/` — that path is reserved for real Claude Code subagent definitions, to avoid a naming collision.)
> **Team decisions and the roadmap live in git:** `.claude/context/decisions.md` is the decision log (one line per agreed decision — read it before changing a gate, threshold, schema or scope), and Section K below summarises the release roadmap. `docs/` is local-only and can drift; the decision log cannot.
> Active project rules and documentation standards are shared in `.agents/rules/`. Claude Code hooks (ownership guard, schema guard, syntax check) live in `.claude/hooks/` and are wired in `.claude/settings.json`. Claude Code subagents live in `.claude/agents/`. Slash commands live in `.claude/commands/`. For Antigravity IDE sessions, `AGENTS.md` at the repo root is the primary discovery file and mirrors all rules.

---

## A. What Unleash Is (and Is Not)

**Unleash** is a multimodal, active challenge-response human verification system. It determines whether a live human is genuinely present in front of a camera and microphone, by issuing a randomized visual + verbal challenge and checking whether the response corroborates across visual, audio, and cross-modal signals.

**It targets:** replay attacks (pre-recorded video), real-time deepfakes (live face-swap), static photo/printout attacks, bot-scripted interactions, and TTS/audio injection. "Targets" is deliberate (decision D-08): until measured, none of these is a proven defence. As of v1, the hard gates demonstrably stop silence, wrong/replayed phrases, wrong head direction and static photos in small-sample tests; TTS injection and real-time face-swap are **not** yet demonstrated to be stopped (Stage 3 and the replay detector are uncalibrated, and Stage 3 showed no genuine-vs-TTS separation). Never describe the system as defending against them without recorded evidence.

**It is explicitly NOT:**
- An identity verification system (does not check *who* someone is)
- A biometric system (no face embeddings or voice prints are stored)
- A continuous monitoring system (point-in-time sessions only, ~15-second challenge window)

**Architecture:** A monolith — FastAPI backend (Railway) + Next.js 14 frontend (Vercel). No microservices. Background work runs via FastAPI `BackgroundTasks`, not Celery/Redis. All ML inference is local and CPU-only — no LLM APIs, no GPU dependencies. Models are pre-trained (silero-vad, faster-whisper tiny, MediaPipe) except the deepfake classifier, a self-trained Xception (team decision; trained on GPU offline, inference forced to CPU, checkpoint distributed outside git). **v1 is a local demo** (decision D-05): Railway/Vercel deployment is a v1.1 task. Models must be present locally at build time (baked into the image) — no runtime model downloads — and Docker uses CPU-only torch wheels (D-20). The Stage 2 model was chosen by bake-off (D-18, D-23): faster-whisper `base.en`, plain (no vocabulary prompt), per-word confidence floor 0.5; update this file when it changes.

---

## B. The Inviolable 4-Key Contract

Every detector module — audio, visual, anti-spoofing — returns **exactly** this schema. No exceptions, no extra required fields, no renamed keys.

```json
{
  "score":  0.92,          // float 0.0–1.0 (1.0 = definitely genuine), or null if errored
  "passed": true,          // bool — this module's own hard-gate / pass-fail evaluation
  "reason": "string",      // human-readable explanation, non-empty
  "error":  null,          // null on success; error string if computation failed (score must be null when error is set)
  "details": {}            // optional, module-specific diagnostic telemetry persisted to the eval store — NOT read by the fusion engine
}
```

Defined in `backend/app/schemas/detector.py` as the Pydantic model `DetectorResult`. **Never** write or approve a module that deviates from this shape. A detector must never raise an uncaught exception — on any failure it returns `{"score": null, "passed": false, "reason": "...", "error": "..."}` instead of crashing.

---

## C. Solo Mode

One person (the owner) currently works on the whole project, so there are no per-module owners and no ownership guard. Any module can be changed when the owner asks for it. The previous three-developer ownership map is preserved at git tag `pre-solo-reset`.

**Returning to three developers:** when the owner says "distribute work among 3", record the decision in `.claude/context/decisions.md`, restore the ownership map and the ownership guard hook from the tag, and split the work as the owner specifies.

---

## D. The Six Signals and Their Gate Types

| # | Signal | Owner | Technique | Gate Type | Weight |
|---|---|---|---|---|---|
| 1 | Visual Liveness | Dev 2 | MediaPipe EAR + blink + micro-movement variance | Soft (weighted) | 20% |
| 2 | Visual Challenge Compliance | Dev 2 | MediaPipe yaw/pitch vs. randomized challenge direction | **HARD GATE** | 25% (score portion) |
| 3 | Deepfake Detection | Dev 3 | Self-trained Xception classifier (FaceForensics++-style data), CPU inference | Soft (joint veto*) | 20% |
| 4 | Replay Detection | Dev 3 | OpenCV FFT moiré + temporal noise + brightness | Soft (joint veto*) | 15% |
| 5 | Audio Speech Gate (Stage 1) | Dev 1 | silero-vad | **HARD GATE** (internal to audio module) | — |
| 5 | Audio Phrase Compliance (Stage 2) | Dev 1 | faster-whisper `base.en` (chosen by bake-off, D-18/D-23) + fuzzy 5-word matching (≥ 4 of 5 words, per-word similarity ≥ 0.8, per-word confidence ≥ 0.5) | **HARD GATE** | — |
| 5 | Voice Authenticity (Stage 3) | Dev 1 | librosa spectral heuristics | Soft (advisory) | 10% |
| 6 | AV Temporal Alignment (Stage 4) | Dev 1 + Dev 2 | Whisper word timestamps × MediaPipe lip openness | Soft (advisory) | 10% |

\* Joint veto: if `deepfake_score < 0.3 AND replay_score < 0.4` simultaneously → `FAILED`, regardless of weighted score.

**Only three things are hard gates at the system level:** Visual Challenge Compliance, Audio Speech Gate, and Audio Phrase Compliance. Everything else is a weighted, soft/advisory signal. When implementing or modifying any module, verify you are not silently turning an advisory signal into a hard gate (or vice versa) — that would be a fusion-engine-level change requiring team agreement (Section G).

**Score thresholds (Dev 3's fusion engine):** `VERIFIED` ≥ 0.80 · `SUSPICIOUS` 0.55–0.79 · `FAILED` < 0.55 or any hard gate failed. Null signals are excluded from the weighted calculation and their weight is redistributed proportionally — never treated as 0.

---

## E. Critical Integration Points Crossing Developer Boundaries

Two data exchanges cross developer boundaries. The intended process was a Day 19 AV-alignment design session between Dev 1 and Dev 2 to agree the exact formats before either side implemented Stage 4 beyond a stub. That session never happened and Dev 2 was unavailable; with explicit user authorization, Dev 1 wrote the agreement solo (based on the shapes the project plan had already specified plus what the real visual/audio code produces) and implemented the real Stage 4 against it. See `.claude/context/audio-pipeline/av-alignment-interface.md` for the finalized schema. If Dev 2 later reviews this and wants changes, that's a new interface negotiation — update that file, `stage-specifications.md`, and this section together in the same commit.

| Data Exchange | Producer | Consumer | Contents |
|---|---|---|---|
| Lip openness series | Dev 2 (MediaPipe) | Dev 1 (Stage 4) | `{"fps": float, "series": [{"frame_index": int, "time_seconds": float, "lip_openness_ratio": float}, ...]}` — face-height-normalized, omits frames with no detected face. `time_seconds` is the real presentation timestamp of the sampled frame (seconds from clip start, same t=0 as the audio). |
| Lip series `time_seconds` (B4, D-19) | Dev 2 (`visual/_frames.py` reads real PyAV timestamps; `_lip_series.py` carries them) | Dev 1 (Stage 4) | **Implemented end to end 2026-10-02** (orchestrator feeds the visual consumers 120 timestamped frames). Verified on a face-less clip only: Stage 4 returns a real score once a session has a detected face. Stage 4 never uses `frame_index / fps` and the lip series never invents a time; no valid `time_seconds` -> `score=None`. Details: `av-alignment-interface.md` §5. |
| Word timestamps | Dev 1 (faster-whisper) | Dev 1's own Stage 4 | List of `{"word": str, "start": float, "end": float, "probability": float}` dicts (not the plan's originally-sketched tuple shape) |

Dev 1's deep audio-pipeline spec — including the stage-by-stage design, the 10 audio test scenarios, known implementation gotchas, the stage-level integration checklist, the automation/prompting workflow, and the finalized AV-alignment interface — lives in **`.claude/context/audio-pipeline/`**. Read that folder in full before writing or modifying anything under `backend/app/modules/audio/`.

---

## F. Evaluation Targets (What "Good" Looks Like)

| Metric | Target |
|---|---|
| True Accept Rate (TAR) | > 85% |
| False Accept Rate (FAR) | < 5% |
| False Reject Rate (FRR) | < 15% |
| Audio Stage 2 (phrase compliance) accuracy | > 90% |
| End-to-end analysis latency (submission → result) | < 20 seconds |
| Audio Stages 1 + 2 combined latency | < 10 seconds |
| Total end-to-end session (browser open → result shown) | < 60 seconds |

Do not optimize any module in a direction that improves one of these numbers while silently violating a hard gate or the 4-key contract.

---

## G. What Must Never Happen Without Team Discussion

- Any change to the 4-key `DetectorResult` schema
- Any change to which signals are hard gates, or their thresholds
- Any change to the fusion engine's weights or the VERIFIED/SUSPICIOUS/FAILED thresholds
- Any change to the single `.webm` blob upload design (one file, video+audio combined, ffmpeg extracts server-side)
- Any GPU-dependent code (shared CPU is a hard constraint — all models are chosen for CPU performance)

If a change like this seems necessary, stop and flag it for team discussion before writing code. If it does get agreed, update **both** this file and the relevant vertical's workspace docs in the same commit — this file is the ground truth Claude reads; the spec docs in `docs/` are the ground truth for the humans, and both must stay in sync.

---

## H. How to Run Locally

**Backend (FastAPI):**
```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```
Health check: http://localhost:8000/health · Interactive docs: http://localhost:8000/docs

**Frontend (Next.js):**
```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```
App: http://localhost:3000

Before attempting any integration test, confirm both servers are actually running (hit `/health`) rather than assuming.

---

## I. Git Workflow (Summary)

- **Never commit directly to `main`.** Main only updates via reviewed PRs, at phase boundaries (Day 8, 22, 30, 40, 45).
- **Never commit directly to the integration branch.** Work happens on feature branches; PRs merge into integration at milestone days.
- Each developer owns one long-lived feature branch: `feature/audio-pipeline` (Dev 1), `feature/visual-pipeline` (Dev 2), `feature/backend-core` (Dev 3). Never work on another developer's feature branch without being explicitly invited.
- Never merge integration into your feature branch without pulling first.
- Commit frequently with specific messages ("Stage 1 VAD: handle empty audio gracefully"), never in one giant end-of-day commit, and never commit broken code (stash instead if mid-change).
- Any change to a shared interface (the 4-key schema, the lip openness/word-timestamp formats once agreed, the session API shape, any fusion threshold) must be announced to the team before committing.

---

## J. Permanent Session Rules (Apply Every Session, No Exceptions)

**J1 — Ask Before Assuming:** Before writing any code or modifying any file, if there is ANY ambiguity in the request, stop and ask the user directly. Consolidate all open questions into a single message. Never fill a gap with an assumption. Never extend scope beyond what was explicitly requested. Full procedure: `.agents/rules/ask_before_assuming.md`.

**J2 — Dead Code Tracking:** After every stage implementation and before any integration PR, run `/dead-code-audit` to find dead functions, unused imports, and dependency drift between `requirements-audio.txt` and actual imports. Only delete after explicit user approval. Always verify with `pytest` after deletion. Full procedure: `.agents/rules/dead_code_tracking.md` and `.claude/commands/dead-code-audit.md`.

**J3 — CI Dependency Sync:** Never edit `ci.yml` in response to a code bug — fix the code. Only edit `ci.yml` when adding a special-case package with a non-standard import name or a system-level dependency. The smoke test reads `requirements-audio.txt` dynamically and self-maintains. Full procedure: `.agents/rules/ci_dependency_sync.md`.

**J4 — Feature Start Protocol:** When the user describes a new feature or stage in 1-2 lines, always read `docs/unleash_project_plan.md` first. If found, generate a structured implementation session prompt. If NOT found, stop and ask for explicit user authorization before writing any code. Use `/start-feature` to invoke this. Full procedure: `.agents/rules/feature_start_protocol.md` and `.claude/commands/start-feature.md`.

**J5 — No Hardcoded Stub Values:** Never write hardcoded constants, magic numeric scores, or fabricated pass/fail values to satisfy a feature requirement, fill a field, or make a test pass. Every computed value must originate from real algorithm or model output. If a stage is not yet implemented, mark it `[STUB]` explicitly in both the inline code comment **and** the module docstring — never return a plausible-looking numeric result that conceals the absence of real computation. Advisory stub fields in the pipeline must not contribute to the final `score` field until their implementing stage is real. Full procedure: `.agents/rules/no_hardcoded_stub_values.md`.

**J6 — SOLID Audio Architecture:** Keep `backend/app/modules/audio/` strictly modular — one responsibility per file (`_io.py` decoding only, `_extraction.py` ffmpeg/probing, `_speech_gate.py`/`_phrase_compliance.py`/`_voice_authenticity.py`/`_av_alignment.py` one stage each, `__init__.py` orchestration only). Runner functions stay under ~40 lines via helpers; all WAV decoding goes through `_io.py`; score arithmetic is isolated in helpers; heavy libs are imported at module level with a graceful fallback flag. Use `/solid-audit` to check. Full procedure: `.agents/rules/solid_audio_pipeline.md`.

**Always-on rule files (not numbered, but apply every session):** `.agents/rules/document_observations.md` (record findings in `docs/audio_pipeline_observations.md` + `docs/worklog.md` after every milestone) and `.agents/rules/commit_message_generation.md` (conventional-commit format, diff-grounded, no "Stage N"/"WIP" labels).

---
## K. Release Roadmap (Summary — full detail in `ROADMAP.md`; this release in `V1_RELEASE_PLAN.md`)

The final deliverable is an **evaluator-ready, deployed, measured** Unleash: the 5-screen flow working end to end, all hard gates verified on real recordings, TAR/FAR/FRR reported per attack species (ISO/IEC 30107-3 style) from a proper sample, and honest documentation of limits. It is reached in three releases; each has an exit gate and nothing starts on a red build.

| Release | Scope | Exit criteria |
|---|---|---|
| **v1.0 — local demo (one day)** | Build green; 5-screen browser flow with camera+mic in one `.webm`; Stage 2 fixed and measured; true-fps lip timing; `/eval` page; VERIFIED end-to-end test; 28-session reduced evaluation. | Hard-gate attacks 0 reach `VERIFIED`/`SUSPICIOUS`; genuine users 6/6 `VERIFIED`; latency < 20 s; CI green with fixtures; tagged `v1.0.0`. Smile/parallax and deployment are **not** in v1 (D-05, D-06). |
| **v1.1 — hardening** | Common-word phrase + word-level alignment (after a bake-off); two-step head-turn sequence; speak-while-turning binding; capture-quality gate; retry limits; smile and parallax as advisory signals; full evaluation (8–10 recordings per scenario, ≥ 3 speakers); replay and Stage 3 calibration; Docker + Railway + Vercel; branch protection. | Measured TAR > 85%, FAR < 5%, FRR < 15%, Stage 2 accuracy > 90% on the full set; public deployment passes the same smoke test. |
| **v2.0 — final long-term deliverable** | Screen-flash reflection challenge (new hard-gate candidate, needs Section G sign-off); pretrained audio spoof detector evaluated offline and adopted only if it separates genuine from TTS; final ISO-style report, technical summary and demo. | Evaluator-ready package: deployed system, results table by attack species, documented limits. |

Every change to a gate, threshold, schema or scope inside this roadmap must be logged in `.claude/context/decisions.md` in the same commit (Section G still applies).

---
