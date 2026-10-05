"""
Properties the 5-word verbal challenge pool must keep (see vocabulary_builder.py).
The pairwise-confusion test is the one that matters for the Stage 2 hard gate: if two pool
words can match each other, one spoken word could satisfy two challenge slots.
"""
import itertools
import math
import re

import pytest

from app.modules.audio._phrase_compliance import MIN_WORD_SIMILARITY, word_similarity_score
from app.modules.audio.vocabulary_builder import (
    BLOCKED_WORDS,
    CHALLENGE_VOCABULARY,
    build_vocabulary,
)

PHRASE_LENGTH = 5


def test_vocabulary_is_unique_lowercase_alpha():
    assert len(CHALLENGE_VOCABULARY) == len(set(CHALLENGE_VOCABULARY))
    assert all(re.fullmatch(r"[a-z]{4,9}", w) for w in CHALLENGE_VOCABULARY)


def test_vocabulary_is_large_enough_for_the_challenge_entropy():
    bits = PHRASE_LENGTH * math.log2(len(CHALLENGE_VOCABULARY))
    assert len(CHALLENGE_VOCABULARY) >= 120
    assert bits > 30  # 5 words from 136 are about 35 bits when drawn in order


def test_vocabulary_is_not_clustered_in_a_few_letters():
    """Regression: the first vocabulary only contained words starting with a or b."""
    assert len({w[0] for w in CHALLENGE_VOCABULARY}) >= 20


def test_vocabulary_has_no_blocked_words():
    assert not BLOCKED_WORDS & set(CHALLENGE_VOCABULARY)


def test_no_two_vocabulary_words_can_match_each_other():
    worst = max(
        (word_similarity_score(a, b), a, b)
        for a, b in itertools.combinations(CHALLENGE_VOCABULARY, 2)
    )
    assert worst[0] < MIN_WORD_SIMILARITY, f"{worst[1]!r} and {worst[2]!r} are interchangeable to Stage 2"


def test_committed_vocabulary_matches_the_builder():
    pytest.importorskip("cmudict")
    assert build_vocabulary() == CHALLENGE_VOCABULARY, (
        "CHALLENGE_VOCABULARY drifted from build_vocabulary(); regenerate and paste it."
    )


def test_no_homophones_in_vocabulary():
    cmudict = pytest.importorskip("cmudict")
    cmu = cmudict.dict()
    strip = lambda phones: tuple(re.sub(r"\d", "", p) for p in phones)  # noqa: E731
    seen = {}
    for word in CHALLENGE_VOCABULARY:
        for pron in cmu[word]:
            key = strip(pron)
            other = seen.setdefault(key, word)  # a word's own stress variants may share a key
            assert other == word, f"{word!r} and {other!r} sound identical"
