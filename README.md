# Unleash

A multimodal, active challenge-response check that a live person is in front of a camera and microphone. A session issues a random visual action (a head turn, looking up or down, or blinking) and a random 5-word phrase; the recording is checked for the action, the words, and signs of replay, deepfake or synthetic voice, and a verdict (`VERIFIED`, `SUSPICIOUS` or `FAILED`) is produced from the combined evidence.

It targets replay, face-swap, photo and synthetic-voice attacks, but none of these is a proven defence yet: see `V1_RELEASE_PLAN.md` for what is measured and what is not. It does not identify anyone and stores no face or voice prints.

## Setup

Needs Python 3.13, Node 20 and `ffmpeg` on the PATH.

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1                 # Windows PowerShell; macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt        # everything: API, audio, video, anti-spoofing (CPU-only torch) and test tools
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

- Health check: http://localhost:8000/health - interactive docs: http://localhost:8000/docs
- The deepfake model checkpoint is not in git (about 250 MB). Put it at `backend/checkpoints/xception_deepfake_best.pth` or set `UNLEASH_XCEPTION_CHECKPOINT`. Without it the deepfake signal reports an error and is left out of the verdict. Expected SHA-256: `cb731a0a53dbdcaddb09ab6855039b24d6e633d723d951d08f566d79a9d1eb0b` (the file is not published yet).
- The first start downloads the speech model (faster-whisper `base.en`) once. The face and deepfake models are loaded when the server starts, so the first request is not slow.
- Settings are read from the environment or `backend/.env` (any folder you start from). Outside `ENVIRONMENT=development` the server refuses to start unless `SECRET_KEY` is a private value of at least 32 characters (for example `openssl rand -hex 32`). Uploads above `MAX_UPLOAD_BYTES` (25 MB) are refused with 413.

**Module demo (development only):** open `/docs`, call `POST /api/v1/verify` with a recording, the visual action it contains and the 5 spoken words; the response lists every detector's score, pass/fail and reason, the verdict and the time of each step. To score a set of clips from the command line: `python tools/measure_clips.py` (clips are listed in `backend/eval/manifest.json`).

**Your own recordings:** save clips from the recorder page (the file name carries the visual action and the 5 words), then add them to a local manifest and measure them. Recordings and that manifest stay out of git (they show faces and voices). The sample clips that are already tracked (`backend/eval/clips`, `backend/tests/fixtures`) are the team's own recordings, kept as test fixtures with the speakers' consent; do not add anyone else's.

```bash
python tools/add_clips.py D:\Downloads --kind genuine --performed "front light, speaker A"   # kinds: genuine, replay, photo, synthetic_voice, wrong_phrase, silence, wrong_direction
python tools/measure_clips.py --manifest eval/calibration.json
```

Tests: `cd backend && python -m pytest tests -q`.

Frontend: a recorder page. Choose the camera, press Start, and follow the three steps (read the words, say them facing the camera, then do the action that appears). It stops by itself after 13 s; **Analyse Clip** uploads the recording and shows the verdict with every signal, and **Save Clip** keeps the file. Start the backend first. The preview on screen is mirrored like a mirror, but the recording is not, and the backend reads it that way: "left" means the person's own left. A camera driver or phone-as-webcam app with its own "mirror" option must have it switched off, or left and right swap.

```bash
cd frontend
npm install
cp .env.example .env.local   # API_ORIGIN: where the dev proxy forwards /api/v1 (default http://127.0.0.1:8000)
npm run dev        # http://localhost:3000
npm run typecheck && npm run build   # what CI runs on every pull request
```

## Detector result contract

Every detector returns the same five-field object (`backend/app/schemas/detector.py`):

```json
{ "score": 0.92, "passed": true, "reason": "Human-readable explanation.", "error": null, "details": {} }
```

`score` is 0.0 (fake) to 1.0 (genuine) or `null`; when `error` is set, `score` is `null`. `details` is diagnostic telemetry.

## Layout

```text
backend/
  app/
    main.py                 FastAPI app (health, sessions, development-only verify)
    orchestrator.py         analyze_media: runs every detector, fuses, times each step
    fusion.py               must-pass checks, joint veto, weighted score, verdict
    db.py  core/            SQLite persistence; config and HMAC session tokens
    api/v1/endpoints/       sessions.py, verify.py
    media/                  load_frames: one video decode for all detectors
    modules/audio/          extraction, speech check, phrase check, voice authenticity, lip sync
    modules/visual/         landmarks, liveness, head-pose challenge, lip series
    modules/antispoof/      deepfake (Xception) and replay detectors, training script
    schemas/                DetectorResult and the session models
  tests/  eval/  tools/     tests and fixtures; sample clips and manifest; measurement tools
frontend/src/app/           Next.js 14 pages
.claude/  .agents/          project rules, commands, domain notes and the decision log
```

Plans: `V1_RELEASE_PLAN.md` (now) and `ROADMAP.md` (to the final deliverable). Decisions: `.claude/context/decisions.md`. Working rules: `CLAUDE.md`.
