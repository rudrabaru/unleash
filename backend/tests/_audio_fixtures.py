"""
Shared audio fixtures for tests that need a *genuine* recording of the current 5-word challenge.

`genuine_5word.webm` is a real human take (audio only, no video track) of
GENUINE_5WORD_PHRASE. It replaces the old "seven four two" digit recording, which can
never satisfy a 5-word challenge (blocker B5). It is audio-only, so it cannot stand in for the
face-visible clip the visual and end-to-end tests need.
"""
from __future__ import annotations

from pathlib import Path

GENUINE_5WORD_WEBM = Path(__file__).resolve().parent / "fixtures" / "genuine_5word.webm"
# Composite: the genuine audio muxed onto the video track of real_742.webm (which has no detectable face).
# For API/orchestrator tests that need a video stream. Audio-only uploads hang frame extraction.
GENUINE_5WORD_NOFACE_VIDEO_WEBM = GENUINE_5WORD_WEBM.with_name("genuine_5word_noface_video.webm")
GENUINE_5WORD_PHRASE = "walnut lantern bicycle maple trumpet"
