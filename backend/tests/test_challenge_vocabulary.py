"""
Properties the 5-word verbal challenge pool must keep (see vocabulary.py and tools/build_vocabulary.py).
The pairwise-confusion tests are the ones that matter for the phrase check: if two pool words can match
each other, one spoken word could satisfy two challenge slots.
"""
import importlib.util
import itertools
import math
import re
from pathlib import Path

import cmudict

from app.modules.audio._phrase_compliance import MIN_WORD_SIMILARITY, word_similarity_score
from app.modules.audio.vocabulary import CHALLENGE_VOCABULARY

PHRASE_LENGTH = 5
TOOL = Path(__file__).resolve().parents[1] / "tools" / "build_vocabulary.py"
_spec = importlib.util.spec_from_file_location("build_vocabulary", TOOL)
build_vocabulary = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_vocabulary)  # the rules and the blocklist live with the tool that applies them

PRONUNCIATIONS = cmudict.dict()


def test_vocabulary_is_unique_lowercase_alpha():
    assert len(CHALLENGE_VOCABULARY) == len(set(CHALLENGE_VOCABULARY))
    assert all(re.fullmatch(r"[a-z]{4,9}", w) for w in CHALLENGE_VOCABULARY)


def test_vocabulary_is_large_enough_for_the_challenge_entropy():
    bits = PHRASE_LENGTH * math.log2(len(CHALLENGE_VOCABULARY))
    assert len(CHALLENGE_VOCABULARY) >= 150
    assert bits > 35  # entropy only stops a pre-recorded phrase; the protocol is what stops a live voice


def test_vocabulary_is_not_clustered_in_a_few_letters():
    """Regression: the first vocabulary only contained words starting with a or b."""
    assert len({w[0] for w in CHALLENGE_VOCABULARY}) >= 18


def test_vocabulary_has_no_number_words_and_nothing_from_the_blocklist():
    """Whisper may transcribe number words as digits, which would never match; the blocklist is words not to show a person."""
    assert not build_vocabulary.NUMBER_WORDS & set(CHALLENGE_VOCABULARY)
    assert not build_vocabulary.BLOCKLIST & set(CHALLENGE_VOCABULARY)


def test_every_word_has_two_or_three_syllables_and_is_in_the_pronunciation_dictionary():
    for word in CHALLENGE_VOCABULARY:
        variants = PRONUNCIATIONS.get(word)
        assert variants, f"{word!r} is not in the CMU Pronouncing Dictionary"
        assert all(build_vocabulary.MIN_SYLLABLES <= build_vocabulary._syllables(v) <= build_vocabulary.MAX_SYLLABLES for v in variants), word


def test_no_two_vocabulary_words_can_match_each_other():
    worst = max(
        (word_similarity_score(a, b), a, b)
        for a, b in itertools.combinations(CHALLENGE_VOCABULARY, 2)
    )
    assert worst[0] < MIN_WORD_SIMILARITY, f"{worst[1]!r} and {worst[2]!r} are interchangeable to the phrase check"
    assert worst[0] < build_vocabulary.MAX_SPELLING_SIMILARITY, f"{worst[1]!r} and {worst[2]!r} are spelled too alike"


def test_no_two_vocabulary_words_sound_alike():
    """No homophones inside the pool, and every pair differs by at least two phonemes."""
    sounds = {w: [build_vocabulary._phonemes(v) for v in PRONUNCIATIONS[w]] for w in CHALLENGE_VOCABULARY}
    for a, b in itertools.combinations(CHALLENGE_VOCABULARY, 2):
        closest = min(build_vocabulary.phoneme_distance(x, y) for x in sounds[a] for y in sounds[b])
        assert closest >= build_vocabulary.MIN_PHONEME_DISTANCE, f"{a!r} and {b!r} sound alike"


def test_the_pool_has_no_plurals_or_ing_forms_of_other_words():
    assert not [w for w in CHALLENGE_VOCABULARY if w.endswith("ing") or (w.endswith("s") and not w.endswith("ss"))]
