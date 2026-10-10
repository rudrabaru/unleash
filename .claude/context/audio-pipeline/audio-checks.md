# Audio checks

What `backend/app/modules/audio/` does and the numbers it uses. If this file and the code disagree, the code is right; fix this file.

**Entry point:** `process_audio_pipeline(media_path, challenge_phrase, lip_openness_data=None, phases=None, recording_start=None) -> DetectorResult` in `backend/app/modules/audio/__init__.py`. A plain (blocking) function. The orchestrator calls only this function, never the individual checks.

```
recording (.webm/.mp4) -> ffmpeg extraction -> 16 kHz mono WAV (temporary folder, always deleted)
  -> speech check        (silero-vad)         MUST PASS
  -> phrase check        (faster-whisper)     MUST PASS
  -> voice authenticity  (librosa heuristics) advisory
  -> lip sync            (word times x lip series) advisory
```

**Windows.** With `phases` (the protocol windows, `app/protocol.py`) the speech, phrase and lip-sync checks use the **Speak window only**: the recording's time 3-8 s widened by the 0.4 s guard before and 0.7 s after (container `[2.6, 8.7]` for a recording that starts at 0). `_speak_crop.py` cuts that part out of the extracted WAV and converts between the three clocks (recording, container, WAV); `details["speak_window"]` says what was listened to. The voice-authenticity check keeps the whole recording. Without `phases` (the `/verify` demo default, older clips) everything is judged as before.

A failed must-pass check stops the pipeline and returns `passed=False` without running the later checks. The advisory checks never change `passed`; they only feed `score` and the fusion engine's weighted score.

## Extraction

- ffmpeg is a subprocess (never a Python wrapper). Output is forced to 16 kHz mono PCM whatever the browser recorded.
- The output is verified (`verify_wav`) and its duration compared with the container's claimed duration: under 50% means truncated (ffmpeg can exit 0 and still lose most of the audio). A container with no duration header skips that check.
- The media probe also reports the audio track's `start_time`; the lip-sync check needs it (see `av-alignment-interface.md`).

## Speech check (`_speech_gate.py`)

- silero-vad, loaded once at import. Passes only if speech is detected and the summed speech time is at least **2.0 s**.
- No score. Details: `speech_detected`, `speech_duration_seconds`, `segment_count`, `segments`, `vad_backend`, `file_duration_seconds`.

## Phrase check (`_phrase_compliance.py`)

- faster-whisper **`base.en`**, int8, CPU, loaded once at import. Plain transcription with word timestamps; **no vocabulary `initial_prompt`** (it made Whisper emit vocabulary words on noise and tones, a way for non-speech to pass).
- Matching (`_phrase_align.py`): an **ordered** alignment (longest common subsequence): the target words must be heard in the challenge's order, each heard word and each target word is used at most once. A recognized word counts if its similarity is **at least 0.8** (edit distance divided by the longer word's length, case and punctuation stripped; dividing by twice the length let about 90% of unrelated sentences pass) **and** its Whisper probability is **at least 0.5**. **4 of 5** target words must match, in order, and **at most 3 heard words may match no target word** (`insertions`; a starting value, to be re-set from the 99th percentile of genuine takes).
- Known limits: reading 40 random vocabulary words in a row no longer covers a challenge (it did 2.6% of the time with a bag of words; 0 of 2,000 now). Isolated rare nouns are still recognised unreliably: the genuine take scores 4/5 at normal pace and 2/5 when sped up 1.25x ("Lenton", "Napole"), which is why the vocabulary is being replaced. Lowering the 0.5 floor needs at least 10 genuine takes from at least 3 speakers (`backend/tools/phrase_model_comparison.py`). On a synthetic text-to-speech proxy (not human speech) base.en plain passed 51/60 at floor 0.5 and 56/60 at 0.3, with 0% false accepts on 2,000 random challenges.
- Details: `phrase_matched`, `words_detected`, `target_words`, `match_count`, `matched_pairs`, `average_confidence`, `insertions`, `max_insertions`, `transcript`, `word_timestamps` (`{word, start, end, probability}`, relative to the checked audio), `phrase_check_latency_seconds`, `speak_window`.

## Voice authenticity (`_voice_authenticity.py`) - advisory, UNCALIBRATED

- Three heuristics on the speech and silence parts: noise-floor consistency (weight 0.30), spectral-flux variance (0.45), high-frequency roll-off (0.25). A heuristic that cannot measure returns `None` and is left out (weights renormalised); if none measure, the result has `score=None` and an error.
- Every threshold and weight is a starting guess. On the only early recordings (two genuine, one text-to-speech) it showed no separation, the flux term saturated at 1.0, and the roll-off term ran backwards. Do not present its score as detection.
- Details: `voice_authenticity_score`, the three sub-scores, `voice_degraded`, `voice_degraded_reasons`, `metrics`.

## Lip sync (`_av_alignment.py`) - advisory, UNCALIBRATED

- For each spoken word, take the lip samples within the word's time window widened by **0.3 s** each side. The word is aligned if at least **30%** of those samples are above a per-session "open" threshold: `median(series) + max(0.02, 0.5 * stdev(series))`. Score = fraction of words that are aligned among words with at least one overlapping sample.
- No usable data (no lip series, no word times, no valid `time_seconds`, no overlap) returns `score=None` with `lip_sync_degraded_reason`; a score is never invented.
- The open threshold assumes a mostly closed mouth, so tests must use a full-length clip with brief open windows. The 0.3 s windows around each word cover most of the speech span, so a mismatched recording may still score high; it needs a control (shuffled or offset audio) before it is trusted.

## Pipeline output

`score` = mean of the voice and lip-sync scores that exist (equal weights), or `None`; fusion does **not** read this score. Fusion reads `details["voice_authenticity_score"]` and `details["av_alignment_score"]`. `passed` is true only if both must-pass checks passed. `details` also carries `lip_sync_latency_seconds`, `audio_start_offset_seconds` and, when an advisory check errored, `voice_check_error` / `lip_sync_error`.

## Latency

Speech plus phrase checks must stay under 10 s (measured about 1 s warm). Whole-request budget: 20 s (measured 8-10 s warm on a 1080p clip). Run `/latency-benchmark` before optimising anything.
