"""
Ordered word alignment for the phrase check.

The recognizer returns the words it heard; the challenge is five words in a given order. A target
word counts as said only if a heard word that is close enough in spelling and confident enough sits
in the same order as the target words. Heard words that match nothing are "insertions": the person
said more than the challenge. Counting both is what stops a person reading many words from the
vocabulary in the hope of covering the challenge by chance (it was about 2.6% at 40 random words
when order and extra words were free).

Matching is the classic longest-common-subsequence alignment, so the result is the best possible
one: no word is used twice, order is never broken, and the number of matches is the largest that
any ordered pairing allows (ties go to the closer spellings).
"""
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Per-word Whisper probability a recognized word needs before it can satisfy a challenge word.
# Kept at 0.5: lowering it changes a must-pass threshold and waits for at least 10 genuine takes
# from at least 3 speakers (tools/phrase_model_comparison.py).
MIN_WORD_CONFIDENCE: float = 0.5

# Minimum per-word similarity for a recognized word to count as a challenge word.
# 0.8 on a 1x-length-normalized edit distance tolerates one slip in a 5+ letter word
# (e.g. "bridget" -> "bridge" = 0.86) but rejects unrelated words. The previous 2x
# normalization floored any two words at 0.5 and let ~90% of filler speech through.
MIN_WORD_SIMILARITY: float = 0.8

# Most heard words that may match no challenge word. A starting value (the filler "um", a repeated
# word, one misheard word): re-set from the 99th percentile of genuine takes once there are enough.
MAX_INSERTED_WORDS: int = 3


def levenshtein_distance(s1: str, s2: str) -> int:
    """Edit distance between two strings (insert, delete or substitute one character costs 1)."""
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])

    return dp[m][n]


def normalize_word(word: str) -> str:
    """Lowercase and strip everything but letters (Whisper emits tokens like 'Apple,')."""
    return re.sub(r"[^a-z]", "", word.lower())


def word_similarity_score(recognized: str, target: str) -> float:
    """
    Word-level similarity (0.0-1.0): 1 - edit_distance / longer_word_length.
    Both words are normalized first, so case and punctuation never affect the score.
    """
    a, b = normalize_word(recognized), normalize_word(target)
    longest = max(len(a), len(b))
    if longest == 0:
        return 1.0
    return max(0.0, 1.0 - levenshtein_distance(a, b) / longest)


@dataclass(frozen=True)
class Alignment:
    match_count: int  # target words said, in order
    pairs: List[str]  # "heard -> target", in spoken order
    insertions: int  # heard words that matched no target word
    average_confidence: float  # of the matched words


def _eligible_similarity(
    heard: Tuple[str, float], target: str, min_word_confidence: float, min_word_similarity: float
) -> Optional[float]:
    """Similarity of a heard word to a target word, or None when it is too unsure or too different to count."""
    word, confidence = heard
    if confidence < min_word_confidence:
        return None
    similarity = word_similarity_score(word, target)
    return similarity if similarity >= min_word_similarity else None


def align_words(
    recognized_words: List[Tuple[str, float]],
    target_words: List[str],
    min_word_confidence: float = MIN_WORD_CONFIDENCE,
    min_word_similarity: float = MIN_WORD_SIMILARITY,
) -> Alignment:
    """
    Best ordered pairing of heard words `(word, confidence)` with the target words.

    A heard word below `min_word_confidence`, or too different from a target word, never matches
    it. The pairing keeps the spoken order, uses each heard word and each target word at most once
    and maximises the number of matches, then the total similarity.
    """
    n, m = len(recognized_words), len(target_words)
    # best[i][j]: (matches, similarity sum) using the first i heard words and the first j targets
    best = [[(0, 0.0)] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            candidates = [best[i - 1][j], best[i][j - 1]]
            similarity = _eligible_similarity(recognized_words[i - 1], target_words[j - 1], min_word_confidence, min_word_similarity)
            if similarity is not None:
                matches, total = best[i - 1][j - 1]
                candidates.append((matches + 1, total + similarity))
            best[i][j] = max(candidates)

    pairs: List[str] = []
    confidence_sum = 0.0
    i, j = n, m
    while i > 0 and j > 0:
        similarity = _eligible_similarity(recognized_words[i - 1], target_words[j - 1], min_word_confidence, min_word_similarity)
        if similarity is not None and best[i][j] == (best[i - 1][j - 1][0] + 1, best[i - 1][j - 1][1] + similarity):
            heard, confidence = recognized_words[i - 1]
            pairs.append(f"{heard} -> {target_words[j - 1]}")
            confidence_sum += confidence
            i, j = i - 1, j - 1
        elif best[i][j] == best[i - 1][j]:
            i -= 1
        else:
            j -= 1

    matches = best[n][m][0]
    pairs.reverse()
    return Alignment(
        match_count=matches,
        pairs=pairs,
        insertions=n - matches,
        average_confidence=confidence_sum / matches if matches else 0.0,
    )
