# Known Tricky Spots — Audio Pipeline

Implementation gotchas identified before coding started. If Claude Code proposes something that contradicts one of these, correct it by pointing back to this file.

1. **faster-whisper model loading.** Must be loaded once at server/module startup, stored in a module-level variable, not reloaded per-request. Loading per-request adds seconds of latency to every single submission and will blow the Stage 1–3 latency budget (< 10s) immediately. If Claude writes code that instantiates the model inside the request-handling function, that's a bug — fix it to load at import time instead.

2. **silero-vad Windows import issues.** silero-vad has occasionally had import/build problems on Windows. If this happens, the pre-approved fallback is `webrtcvad`. This substitution does **not** require a team discussion — it's already agreed in the project plan as the sanctioned fallback path. Document which one is actually in use in this file and in code comments if a fallback is triggered.

3. **Digit matching is not string matching.** The Stage 2 digit-matching logic must handle: digit-by-digit pronunciation ("seven, four, two"), combined/number-word pronunciation ("seven forty-two", "seven hundred forty-two"), and hesitation ("seven... four... two"). A naive substring or exact-match comparison against the transcript will fail on all of these and produce an unacceptable false-reject rate. See `stage-specifications.md` Stage 2 for the actual matching algorithm (2-of-3 digit threshold).

4. **Model load time vs. token expiry.** The HMAC challenge token has a 2-minute expiry (see root `CLAUDE.md` and `backend/app/core/security.py`). faster-whisper's first-load delay (15–30 seconds) must never happen inside the request path — it must be fully absorbed at server startup, before any token is ever issued. If Claude sees model loading anywhere near request handling, that's the same class of bug as #1.

5. **ffmpeg is a subprocess, not a library.** Audio extraction from the `.webm` blob must invoke `ffmpeg` as a subprocess call, not use a Python ffmpeg-wrapper package as the actual decode/resample engine. The output WAV must always be forced to exactly 16kHz mono, regardless of what the browser's `MediaRecorder` actually captured — never trust the browser-side sample rate hint.
