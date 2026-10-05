"""Locations of the tracked test fixtures and the phrase the genuine recording speaks."""
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
VIDEO_FIXTURES_DIR = FIXTURES_DIR / "video"  # real-face clips: head turns, looking up/down, blinking

# A real human take of GENUINE_5WORD_PHRASE. Audio only (no video track).
GENUINE_5WORD_WEBM = FIXTURES_DIR / "genuine_5word.webm"
# The same audio on a browser-style VP8 video track that contains no face. Use it whenever a
# test needs a video source (frames, landmarks with no face, session upload, ...).
GENUINE_5WORD_NOFACE_VIDEO_WEBM = FIXTURES_DIR / "genuine_5word_noface_video.webm"
GENUINE_5WORD_PHRASE = "walnut lantern bicycle maple trumpet"
# A valid 5-word challenge that the genuine recording does NOT speak.
OTHER_5WORD_PHRASE = "apple bridge cloud dark eagle"


def require(path: Path) -> Path:
    """Return a tracked fixture path, failing (not skipping) when it is missing."""
    assert path.exists(), f"tracked test fixture is missing: {path}"
    return path
