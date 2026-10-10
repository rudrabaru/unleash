# Recording the pilot and calibration takes

These are the steps that need a person at a camera. Everything the system does with the recordings afterwards is automatic. Recordings show faces and voices: they stay on your machine (`eval/recordings/` is ignored by git); ask each speaker first.

## Before you start
1. Backend: `cd backend && cp .env.example .env` (once), then `uvicorn app.main:app --port 8000`.
2. Frontend: in `frontend/.env.local` **delete any `NEXT_PUBLIC_API_BASE_URL` line** (the default is the same-origin proxy), then
   `NEXT_PUBLIC_DEBUG=1 npm run dev` (PowerShell: `$env:NEXT_PUBLIC_DEBUG = "1"; npm run dev`). The debug flag adds the **Save recording** button and the raw scores.
3. Use Chrome, Edge or Firefox on a computer, with the camera at eye level and light on your face.

## 1. Direction fixtures (a few minutes, once per camera)
Record on each of **two different cameras** (for example the laptop webcam and a phone used as a webcam, with its own "mirror" option **off**): keep going until you have saved one clip whose challenge was `TURN_HEAD_LEFT` and one `TURN_HEAD_RIGHT`. Do the movement as shown (turn, hold, come back). Save each with **Save recording**. Tell me the file names and which camera each came from; they become test fixtures that prove "left" means your left through the real browser path.

## 2. Pilot takes (about 30)
Three speakers, about ten genuine takes each: do exactly what the screen asks, as you naturally would, with a mix of the five actions, some in dimmer light, some a bit faster. Save every take, including the ones that fail: failures are the point.

Then, from `backend/`:

```
.venv\Scripts\python.exe tools/add_clips.py D:\Downloads --kind genuine --speaker A --device "laptop webcam, Chrome" --performed "front light"
.venv\Scripts\python.exe tools/measure_clips.py --manifest eval/calibration.json --json eval/pilot_results.json
```

(`--speaker` and `--device` matter: the calibration is validated one speaker at a time.) Send me `eval/pilot_results.json`, or just say it is there; it contains no faces or voices (scores, counts and codes only).

## 3. What the pilot decides
- the **window guard** (0.4 s) and the **speaking allowance** (0.7 s), from where words and movements really fall against the windows;
- whether **base.en** hears the new words well enough across your accents, or whether a larger speech model is worth its time;
- the **hold and return** tolerances and the **insertion cap** (3 extra words), from genuine takes;
- whether five seconds of Speak is enough for a normal-paced read of five words.

## 4. Later: attacks (the calibration campaign)
Phone or monitor replay of a genuine take, a printed or on-screen photo with a live voice, a synthetic voice over a live face, wrong words, silence, wrong direction and no movement, recorded through the same recorder and added with the matching `--kind`. The plan and the numbers are in `V1_RELEASE_PLAN.md` (P2).
