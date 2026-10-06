# Rule: detector contract and must-pass checks

Applies to every change under `backend/app/modules/` and `backend/app/fusion.py`.

- Every detector returns exactly the `DetectorResult` in `backend/app/schemas/detector.py` (`score`, `passed`, `reason`, `error`, optional `details`). When `error` is set, `score` is `None`. A detector never raises; on failure it returns `score=None, passed=False, reason, error`.
- Only three things are must-pass checks: the visual challenge, the audio speech check and the audio phrase check. Everything else is a weighted advisory signal. Never turn an advisory signal into a must-pass check, or the reverse, without the owner's explicit approval and a line in `.claude/context/decisions.md`.
- The same approval and decision-log line are needed to change a threshold, a fusion weight, the verdict bands or the contract itself.
- Detectors are plain blocking functions (no `async def`); the models they share are loaded once at import and only one analysis runs at a time.
- Keep each file to one job (decoding in `audio/_io.py`, ffmpeg in `audio/_extraction.py`, video decoding in `media/frames.py`) and functions to about 40 lines. `/solid-audit` checks this.
