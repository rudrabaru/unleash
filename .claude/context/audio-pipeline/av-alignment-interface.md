# Lip series and word-time interface (video side to lip-sync check)

The agreed shapes passed between the visual module and the audio module's lip-sync check, and the clock they share. If another module's code changes either shape, change this file in the same commit.

## 1. Lip openness series (visual module to lip-sync check)

Built by `backend/app/modules/visual/_lip_series.py::build_lip_series(features, fps)` from the landmark features that `extract_landmark_features` computes on the dense frames, and passed to `process_audio_pipeline(..., lip_openness_data=...)`.

```python
{
  "fps": 29.97,   # informational only; the lip-sync check never uses it
  "series": [
    {"frame_index": 0,  "time_seconds": 0.00, "lip_openness_ratio": 0.041},
    {"frame_index": 15, "time_seconds": 0.51, "lip_openness_ratio": 0.038},
    ...
  ]
}
```

- `lip_openness_ratio` = distance between the inner-lip landmarks 13 and 14, divided by face height (forehead 10 to chin 152). Unitless, roughly 0.02 closed to 0.25+ wide open; there is no absolute threshold (see the lip-sync check's per-session threshold).
- `frame_index` is the position of the frame in the decoded stream. It is a label only: **never convert it to a time with `/ fps`** (browser `.webm` reports a bogus 1000 fps through OpenCV, and the index counts decoded frames).
- `time_seconds` is the frame's real presentation time on the **container clock**, read with PyAV. A frame with no real timestamp is dropped by the loader, and a time is never invented. Frames with no detected face are omitted (not zero-filled). An empty series is valid input: the lip-sync check then returns `score=None`.

## 2. Word timestamps (phrase check to lip-sync check)

`details["word_timestamps"]` of the phrase check: a list of dicts `{"word": str, "start": float, "end": float, "probability": float}`. `start` and `end` are seconds **relative to the extracted WAV**, whose first sample is the first sample of the audio track.

## 3. One clock

The lip series is on the container clock; word times are relative to the WAV. The audio track can start later than the container's zero (a probe with the audio delayed by 0.3 s showed the WAV placing a tone at 1.0 s that is at 1.3 s on the container clock). Before the lip-sync check, `to_container_time` adds the audio track's `start_time` (from ffprobe; an Opus pre-skip below zero counts as zero) to every word time, and the applied offset is recorded in `details["audio_start_offset_seconds"]`. `tests/test_clock_alignment.py` pins this with synthetic flash-and-tone clips. A late *video* start needs no correction: PyAV frame times already include it.

## 4. Matching rules (what the code does)

For each word `{start, end}`: window `[start - 0.3, end + 0.3]`; collect lip samples whose `time_seconds` is in the window; the word is aligned if at least 30% of them exceed `median(series) + max(0.02, 0.5 * stdev(series))`. Score = aligned words / words with at least one overlapping sample. Words with no overlapping sample are left out of both counts. The check is advisory: `passed` is always true.

## 5. Degraded results (never a made-up score)

| Condition | Result |
|---|---|
| no lip series, or an empty `series` | `score=None`, `lip_sync_degraded_reason` set |
| no word timestamps | `score=None`, `lip_sync_degraded_reason` set |
| no sample with a finite, non-negative `time_seconds` | `score=None`, reason names `time_seconds` |
| every word has zero overlapping samples | `score=None`, reason set |
| otherwise | a fraction in [0, 1] |

Tests: `tests/test_av_alignment.py` (matching and degraded cases), `tests/test_lip_series.py` (series contents), `tests/test_clock_alignment.py` (the shared clock), `tests/test_frame_loader.py` (real timestamps).
