"""
Tests for the phrase check (faster-whisper transcription plus ordered, fuzzy 4-of-5 word matching).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.audio import _phrase_compliance as _pc
from app.modules.audio import process_audio_pipeline
from app.modules.audio._extraction import extract_wav
from app.modules.audio.vocabulary import CHALLENGE_VOCABULARY
from app.modules.audio._phrase_compliance import (
    _WHISPER_MODEL,
    levenshtein_distance,
    word_similarity_score,
    align_words,
    run_phrase_compliance,
)
from app.schemas.detector import DetectorResult
from _paths import GENUINE_5WORD_PHRASE, GENUINE_5WORD_WEBM, OTHER_5WORD_PHRASE, require


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


TARGET = ["apple", "bridge", "cloud", "dark", "eagle"]


def _tokens(words, confidence=0.9):
    return [(w, confidence) for w in words]


def test_align_perfect_phrase_in_order():
    recognized = [("apple", 0.95), ("bridge", 0.92), ("cloud", 0.88), ("dark", 0.91), ("eagle", 0.89)]
    found = align_words(recognized, TARGET, min_word_confidence=0.5, min_word_similarity=0.6)
    assert found.match_count == 5 and found.insertions == 0
    assert found.average_confidence > 0.85
    assert found.pairs == ["apple -> apple", "bridge -> bridge", "cloud -> cloud", "dark -> dark", "eagle -> eagle"]


def test_align_accepts_one_slip_in_spelling():
    recognized = [("apple", 0.95), ("bridget", 0.70), ("cloud", 0.88), ("dark", 0.91), ("eagle", 0.89)]
    found = align_words(recognized, TARGET, min_word_confidence=0.5, min_word_similarity=0.6)
    assert found.match_count == 5  # "bridget" -> "bridge"


def test_align_skips_a_low_confidence_word_and_counts_it_as_an_insertion():
    recognized = [("apple", 0.95), ("wrong", 0.2), ("cloud", 0.88), ("dark", 0.91), ("eagle", 0.89)]
    found = align_words(recognized, TARGET, min_word_confidence=0.5, min_word_similarity=0.6)
    assert found.match_count == 4  # "wrong" is skipped due to its low confidence
    assert found.insertions == 1


def test_match_rejects_filler_speech():
    """Regression: the old 2x-normalized metric accepted ~90% of unrelated sentences."""
    filler = "so i think that the best thing to do is just say a bunch of random words".split()
    assert align_words(_tokens(filler), TARGET).match_count < 4


def test_match_rejects_a_previous_sessions_phrase():
    """Replay defence: a phrase from another session must not satisfy this session's challenge."""
    found = align_words(_tokens(["above", "banner", "river", "stone", "orange"]), TARGET)
    assert found.match_count < 4


def test_match_rejects_three_of_five():
    found = align_words(_tokens(["apple", "bridge", "cloud", "river", "stone"]), TARGET)
    assert found.match_count == 3


def test_match_accepts_case_punctuation_and_one_slip():
    recognized = [("Apple,", 0.9), ("Bridge.", 0.9), ("clouds", 0.9), ("dark", 0.9), ("eagle", 0.9)]
    assert align_words(recognized, TARGET).match_count == 5


def test_match_does_not_reuse_one_spoken_word():
    """Saying one challenge word five times must not match five target words."""
    found = align_words(_tokens(["apple"] * 5), ["apple", "apple", "cloud", "dark", "eagle"])
    assert found.match_count == 2


def test_the_words_must_come_in_the_challenge_order():
    """The challenge is five words IN ORDER: the same words in another order are not the phrase."""
    reversed_phrase = list(reversed(TARGET))
    found = align_words(_tokens(reversed_phrase), TARGET)
    assert found.match_count == 1  # only a single word can stay in order

    swapped = ["bridge", "apple", "cloud", "dark", "eagle"]
    assert align_words(_tokens(swapped), TARGET).match_count == 4  # one swap still leaves 4 in order


def test_extra_words_around_the_phrase_are_counted_not_forgiven():
    around = ["um", "apple", "bridge", "cloud", "dark", "eagle", "ok", "thanks"]
    found = align_words(_tokens(around), TARGET)
    assert found.match_count == 5 and found.insertions == 3


def test_reading_many_vocabulary_words_does_not_pass_by_chance():
    """
    Regression for the bag-of-words matcher: reading 40 random vocabulary words covered the challenge
    2.6% of the time. In order, with at most 3 extra words allowed, it must not.
    """
    import random

    rng = random.Random(7)
    accepted = 0
    for _ in range(2000):
        challenge = rng.sample(CHALLENGE_VOCABULARY, 5)
        said = rng.sample(CHALLENGE_VOCABULARY, 40)
        found = align_words(_tokens(said), challenge)
        accepted += found.match_count >= 4 and found.insertions <= _pc.MAX_INSERTED_WORDS
    assert accepted == 0


def test_a_take_with_too_many_extra_words_fails_even_when_the_phrase_is_in_it(monkeypatch, tmp_path):
    from types import SimpleNamespace

    heard = ["so", "um", "apple", "bridge", "cloud", "dark", "eagle", "yeah", "right"]
    words = [SimpleNamespace(word=w, start=float(i), end=i + 0.5, probability=0.9) for i, w in enumerate(heard)]
    segment = SimpleNamespace(text=" ".join(heard), words=words)
    monkeypatch.setattr(_pc, "_transcribe", lambda path: ([segment], SimpleNamespace(language="en"), 0.1))
    wav = tmp_path / "speech.wav"
    wav.write_bytes(b"RIFF")

    result = run_phrase_compliance(wav, " ".join(TARGET))

    assert result.details["match_count"] == 5 and result.details["insertions"] == 4
    assert result.passed is False and result.error is None
    assert "extra words" in result.reason


def test_recognizer_settings_are_the_agreed_ones():
    """base.en, no vocabulary prompt, 0.5 per-word floor. Changing the floor needs the owner's approval."""
    assert _pc.WHISPER_MODEL_NAME == "base.en"
    assert _pc.MIN_WORD_CONFIDENCE == 0.5
    assert _pc.MIN_WORD_SIMILARITY == 0.8


@pytest.mark.parametrize("fixture", ["tone_webm", "silence_webm"])
def test_non_speech_never_produces_challenge_words(fixture, request, tmp_path):
    """The rejected `initial_prompt` approach made Whisper emit vocabulary words on tones/noise."""
    src = request.getfixturevalue(fixture)
    wav = tmp_path / "clip_16k.wav"
    ok, err, _ = extract_wav(src, wav)
    assert ok, err
    res = run_phrase_compliance(wav, GENUINE_5WORD_PHRASE)
    assert res.error is None
    assert not set(w.lower().strip(".,?!") for w in res.details["words_detected"]) & set(CHALLENGE_VOCABULARY)
    assert res.passed is False


def test_genuine_take_passes_the_phrase_check(genuine_wav):
    """Regression: a real genuine take that the multilingual tiny model failed (3/5: 'Lenton', 'Nappal')."""
    res = run_phrase_compliance(genuine_wav, GENUINE_5WORD_PHRASE)
    assert res.error is None
    assert res.details["match_count"] >= 4, res.reason
    assert res.passed is True
    assert res.details["whisper_model"] == "base.en"


def test_invalid_challenge_phrase(tmp_path):
    """A challenge phrase that is not exactly 5 words returns an error."""
    res = run_phrase_compliance(tmp_path / "unused.wav", "apple bridge cloud")
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None
    assert res.error == "Invalid challenge phrase format"


def test_nonexistent_audio_file():
    """Test missing WAV file is handled gracefully."""
    fake_wav = Path("nonexistent_path_audio_123.wav")
    res = run_phrase_compliance(fake_wav, OTHER_5WORD_PHRASE)
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.score is None
    assert res.error == "Audio file does not exist"


def test_real_fixture_returns_word_timestamps(genuine_wav):
    """Transcription keeps word-level timestamps (the lip-sync check needs them)."""
    res = run_phrase_compliance(genuine_wav, GENUINE_5WORD_PHRASE)
    assert isinstance(res, DetectorResult)
    assert res.error is None
    assert res.details is not None
    assert len(res.details["word_timestamps"]) > 0
    assert res.details["target_words"] == GENUINE_5WORD_PHRASE.split()


def test_wrong_phrase_fails(genuine_wav):
    """Speech that does not match the issued challenge fails the phrase check."""
    res = run_phrase_compliance(genuine_wav, OTHER_5WORD_PHRASE)
    assert isinstance(res, DetectorResult)
    assert res.error is None
    assert res.details is not None
    assert res.details["phrase_matched"] is False


def test_pipeline_rejects_speech_that_does_not_match_the_challenge():
    """Through the whole audio pipeline a wrong phrase is a failure, not an error."""
    res = process_audio_pipeline(str(require(GENUINE_5WORD_WEBM)), OTHER_5WORD_PHRASE)
    assert isinstance(res, DetectorResult)
    assert res.passed is False
    assert res.error is None
    assert res.details is not None
    assert res.details["speech_detected"] is True
    assert res.details["phrase_matched"] is False
