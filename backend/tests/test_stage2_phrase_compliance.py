"""
Unit and integration tests for Stage 2 Phrase Compliance (faster-whisper word matching).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.modules.audio import process_audio_pipeline
from app.modules.audio._phrase_compliance import (
    _WHISPER_MODEL,
    levenshtein_distance,
    word_similarity_score,
    match_words_fuzzy,
    run_phrase_compliance,
)
from app.schemas.detector import DetectorResult

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "prototypes" / "fixtures"
OUT_DIR = Path(__file__).resolve().parent.parent / "prototypes" / "out"


def test_whisper_model_loaded():
    """Verify faster-whisper model is loaded once at module initialization."""
    assert _WHISPER_MODEL is not None, "Whisper model should be loaded at module initialization"


def test_levenshtein_distance():
    """Test edit distance computation."""
    # Identical words
    assert levenshtein_distance("apple", "apple") == 0

    # Single character differences
    assert levenshtein_distance("cat", "bat") == 1
    assert levenshtein_distance("cat", "cats") == 1

    # Multiple differences
    assert levenshtein_distance("kitten", "sitting") == 3

    # Empty strings
    assert levenshtein_distance("", "") == 0
    assert levenshtein_distance("hello", "") == 5


def test_word_similarity_score():
    """Test word-level fuzzy matching similarity."""
    # Identical words
    assert word_similarity_score("apple", "apple") == 1.0

    # Very similar words (1 character difference)
    sim_cat_bat = word_similarity_score("cat", "bat")
    assert 0.5 < sim_cat_bat < 1.0

    # Unrelated words must score well below the match cut-off
    sim_apple_orange = word_similarity_score("apple", "orange")
    assert sim_apple_orange < 0.4

    # Case and punctuation (Whisper emits tokens like "Apple,") never change the score
    assert word_similarity_score("Apple,", "apple") == 1.0


def test_match_words_fuzzy():
    """Test fuzzy word matching algorithm."""
    # Perfect match: all 5 words recognized with high confidence
    recognized = [("apple", 0.95), ("bridge", 0.92), ("cloud", 0.88), ("dark", 0.91), ("eagle", 0.89)]
    target = ["apple", "bridge", "cloud", "dark", "eagle"]
    match_count, pairs, avg_conf = match_words_fuzzy(recognized, target, min_avg_confidence=0.5, min_word_similarity=0.6)
    assert match_count == 5
    assert avg_conf > 0.85

    # 4 of 5 match (passing hard gate, threshold=4)
    recognized = [("apple", 0.95), ("bridget", 0.70), ("cloud", 0.88), ("dark", 0.91), ("eagle", 0.89)]
    target = ["apple", "bridge", "cloud", "dark", "eagle"]
    match_count, pairs, avg_conf = match_words_fuzzy(recognized, target, min_avg_confidence=0.5, min_word_similarity=0.6)
    assert match_count >= 4  # "bridget" -> "bridge" with fuzzy match

    # Low confidence words filtered out
    recognized = [("apple", 0.95), ("wrong", 0.2), ("cloud", 0.88), ("dark", 0.91), ("eagle", 0.89)]
    target = ["apple", "bridge", "cloud", "dark", "eagle"]
    match_count, pairs, avg_conf = match_words_fuzzy(recognized, target, min_avg_confidence=0.5, min_word_similarity=0.6)
    assert match_count == 4  # "wrong" skipped due to low confidence


def _tokens(words):
    return [(w, 0.9) for w in words]


def test_match_rejects_filler_speech():
    """Regression: the old 2x-normalized metric accepted ~90% of unrelated sentences."""
    filler = "so i think that the best thing to do is just say a bunch of random words".split()
    count, _, _ = match_words_fuzzy(_tokens(filler), ["apple", "bridge", "cloud", "dark", "eagle"])
    assert count < 4


def test_match_rejects_a_previous_sessions_phrase():
    """Replay defence: a phrase from another session must not satisfy this session's challenge."""
    count, _, _ = match_words_fuzzy(_tokens(["above", "banner", "river", "stone", "orange"]),
                                    ["apple", "bridge", "cloud", "dark", "eagle"])
    assert count < 4


def test_match_rejects_three_of_five():
    count, _, _ = match_words_fuzzy(_tokens(["apple", "bridge", "cloud", "river", "stone"]),
                                    ["apple", "bridge", "cloud", "dark", "eagle"])
    assert count == 3


def test_match_accepts_case_punctuation_and_one_slip():
    recognized = [("Apple,", 0.9), ("Bridge.", 0.9), ("clouds", 0.9), ("dark", 0.9), ("eagle", 0.9)]
    count, _, _ = match_words_fuzzy(recognized, ["apple", "bridge", "cloud", "dark", "eagle"])
    assert count == 5


def test_match_does_not_reuse_one_spoken_word():
    """Saying one challenge word five times must not match five target words."""
    count, _, _ = match_words_fuzzy(_tokens(["apple"] * 5), ["apple", "apple", "cloud", "dark", "eagle"])
    assert count == 2


def test_invalid_challenge_phrase():
    """Test invalid challenge phrase format (not 5 words) returns error."""
    fake_wav = OUT_DIR / "real_742_16k.wav"
    res = run_phrase_compliance(fake_wav, "apple bridge cloud")
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None
    assert res.error == "Invalid challenge phrase format"


def test_nonexistent_audio_file():
    """Test missing WAV file is handled gracefully."""
    fake_wav = Path("nonexistent_path_audio_123.wav")
    res = run_phrase_compliance(fake_wav, "apple bridge cloud dark eagle")
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None
    assert res.error == "Audio file does not exist"


def test_run_phrase_compliance_real_fixture():
    """Test Stage 2 on real speech WAV fixture ('seven four two')."""
    wav_path = OUT_DIR / "real_742_16k.wav"
    if not wav_path.exists():
        pytest.skip(f"Fixture {wav_path} not found")

    # Test with a 5-word phrase (matching the new interface)
    challenge_phrase = "apple bridge cloud dark eagle"
    res = run_phrase_compliance(wav_path, challenge_phrase)
    assert isinstance(res, DetectorResult)
    assert res.error is None
    assert res.details is not None
    assert "word_timestamps" in res.details
    assert len(res.details["word_timestamps"]) > 0
    assert res.details["target_words"] == challenge_phrase.lower().split()


def test_run_phrase_compliance_wrong_phrase_fail():
    """Test Stage 2 with wrong challenge phrase."""
    wav_path = OUT_DIR / "real_742_16k.wav"
    if not wav_path.exists():
        pytest.skip(f"Fixture {wav_path} not found")

    # Challenge phrase that doesn't match the spoken content
    challenge_phrase = "wrong alpha beta gamma delta"
    res = run_phrase_compliance(wav_path, challenge_phrase)
    assert isinstance(res, DetectorResult)
    assert res.error is None
    assert res.details is not None
    assert res.details["phrase_matched"] is False


def test_pipeline_integration_phrase_match():
    """Test complete audio pipeline with word-phrase challenge."""
    real_webm = FIXTURES_DIR / "real_742.webm"
    if not real_webm.exists():
        pytest.skip(f"Fixture {real_webm} not found")

    # Test with a 5-word phrase
    challenge_phrase = "apple bridge cloud dark eagle"
    res = asyncio.run(process_audio_pipeline(str(real_webm), challenge_phrase))
    assert isinstance(res, DetectorResult)
    assert res.error is None
    assert res.details is not None
    assert res.details["speech_detected"] is True
    assert "word_timestamps" in res.details
    assert len(res.details["word_timestamps"]) > 0


def test_pipeline_integration_wrong_phrase():
    """Test complete audio pipeline with wrong challenge phrase."""
    real_webm = FIXTURES_DIR / "real_742.webm"
    if not real_webm.exists():
        pytest.skip(f"Fixture {real_webm} not found")

    # Wrong challenge phrase will fail the hard gate
    challenge_phrase = "wrong alpha beta gamma delta"
    res = asyncio.run(process_audio_pipeline(str(real_webm), challenge_phrase))
    assert isinstance(res, DetectorResult)
    assert res.error is None
    assert res.details is not None
    assert res.details["speech_detected"] is True
    # Hard gate failure
    assert res.details["phrase_matched"] is False
