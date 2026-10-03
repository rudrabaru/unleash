"""
Audio challenge vocabulary and its offline builder.

`CHALLENGE_VOCABULARY` is the word pool the 5-word verbal challenge is drawn from
(`POST /sessions`). It is generated once by `build_vocabulary()` and committed as a
constant; the runtime never imports the builder's dev-only dependency.

Why a curated pool: challenge entropy is what resists replay and scripted attacks, and a
small vocabulary of acoustically distinct words keeps the small Stage 2 Whisper model
near its best accuracy. A word is only admitted if it
  * has a CMU Pronouncing Dictionary entry and no homophone anywhere in that dictionary
    (so "by"/"buy"/"bye"-style collisions cannot occur),
  * has at least two syllables (one-syllable words are the most confusable for small Whisper models),
  * is not blocklisted (number words, which Whisper may transcribe as digits, and words
    unsuitable to show a user), and
  * differs from every already-selected word by at least MIN_PHONEME_DISTANCE phonemes and
    is spelled differently enough (similarity < MAX_SPELLING_SIMILARITY) that the Stage 2
    matcher can never confuse two pool words.

Regenerate (dev only): `pip install cmudict`, run
`python -m app.modules.audio.vocabulary_builder`, and paste the printed list over
`CHALLENGE_VOCABULARY`. Selection is deterministic for a given BUILD_SEED.
"""
from __future__ import annotations

import random
from typing import Dict, List, Sequence, Tuple

BUILD_SEED = 7
MIN_PHONEME_DISTANCE = 2
# Must stay below Stage 2's MIN_WORD_SIMILARITY so one spoken word can never satisfy two pool words.
MAX_SPELLING_SIMILARITY = 0.7
MAX_VOCAB_SIZE = 200

# Hand-picked concrete, common, easy-to-say English words spread across a-z.
SEED_WORDS: Tuple[str, ...] = tuple((
    "anchor apple arrow autumn anvil acorn alley amber ankle apron artist attic album "
    "bakery balloon banana basket beaver bicycle blanket bridge bucket butter button branch breeze bottle "
    "cabin camera candle canyon carpet castle cherry copper cotton cradle crystal curtain cactus "
    "daisy desert diamond dinner dolphin donkey dragon drawer doctor dozen "
    "eagle echo elbow engine envelope ember elephant emerald "
    "falcon feather fiddle finger flower forest fountain freckle fabric ferry "
    "galaxy garden garlic ginger glacier goblet gravel guitar giraffe gadget "
    "hammer harbor hazel helmet honey horizon hotel hammock harvest "
    "igloo island ivory insect indigo inkwell "
    "jacket jaguar jasmine jelly jigsaw jungle jewel journey "
    "kettle kitten kingdom kayak kernel knight koala kitchen "
    "ladder lantern lemon lizard locket lumber lagoon lavender library "
    "magnet marble meadow mirror monkey mountain muffin mustard maple melon "
    "napkin needle nectar nickel noodle nutmeg narrow nephew "
    "oasis ocean olive onion orange orchid otter oyster outfit "
    "paddle parrot pebble pencil penguin pepper piano pillow planet pumpkin puzzle pocket "
    "quartz quiver quilt quarry quail "
    "rabbit radish rainbow ribbon river rocket rooster ruby "
    "saddle salmon shadow silver spider spoon squirrel sunset sweater sailor sandal "
    "table teapot thunder ticket tiger tomato tractor trumpet turtle tunnel "
    "umbrella unicorn uniform utensil upstairs "
    "valley velvet village violin volcano vinegar vessel vanilla "
    "wagon walnut whistle window winter wizard wallet willow waffle walrus "
    "yellow yogurt yacht yarn "
    "zebra zipper zigzag zucchini zenith"
).split())

# Number words (Whisper may emit digits) and words unsuitable to show a user.
BLOCKED_WORDS = frozenset(
    "one two three four five six seven eight nine ten eleven twelve zero dozen hundred thousand "
    "dagger bomb gun knife blood death".split()
)


def _strip_stress(phones: Sequence[str]) -> Tuple[str, ...]:
    return tuple("".join(ch for ch in p if not ch.isdigit()) for p in phones)


def _syllables(phones: Sequence[str]) -> int:
    return sum(1 for p in phones if p[-1].isdigit())


def _edit_distance(a: Sequence[str], b: Sequence[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def _spelling_similarity(a: str, b: str) -> float:
    return 1.0 - _edit_distance(a, b) / max(len(a), len(b))


def _homophone_index(cmu: Dict[str, List[List[str]]]) -> Dict[Tuple[str, ...], set]:
    index: Dict[Tuple[str, ...], set] = {}
    for word, prons in cmu.items():
        for pron in prons:
            index.setdefault(_strip_stress(pron), set()).add(word)
    return index


def build_vocabulary(
    min_phoneme_distance: int = MIN_PHONEME_DISTANCE,
    max_vocab_size: int = MAX_VOCAB_SIZE,
    seed: int = BUILD_SEED,
) -> List[str]:
    """Return the filtered, alphabetically sorted vocabulary. Deterministic for a given seed."""
    import cmudict  # dev-only dependency; see module docstring

    cmu = cmudict.dict()
    homophones = _homophone_index(cmu)

    admissible: Dict[str, Tuple[str, ...]] = {}
    for word in sorted(set(SEED_WORDS)):
        prons = cmu.get(word)
        if not prons or word in BLOCKED_WORDS or not 4 <= len(word) <= 9:
            continue
        if _syllables(prons[0]) < 2:
            continue
        if any(homophones[_strip_stress(p)] - {word} for p in prons):
            continue
        admissible[word] = _strip_stress(prons[0])

    order = sorted(admissible)
    random.Random(seed).shuffle(order)  # a-z coverage: never alphabetical-greedy

    selected: List[str] = []
    for word in order:
        if all(
            _edit_distance(admissible[word], admissible[s]) >= min_phoneme_distance
            and _spelling_similarity(word, s) < MAX_SPELLING_SIMILARITY
            for s in selected
        ):
            selected.append(word)
            if len(selected) >= max_vocab_size:
                break
    return sorted(selected)


# Generated by build_vocabulary() (seed 7, min phoneme distance 2): 136 words, 25 letters.
CHALLENGE_VOCABULARY: List[str] = [
    "acorn", "album", "ankle", "anvil", "apron", "artist",
    "attic", "autumn", "bakery", "balloon", "banana", "basket",
    "bicycle", "bucket", "butter", "button", "cabin", "cactus",
    "carpet", "cradle", "dinner", "dolphin", "dragon", "eagle",
    "elbow", "elephant", "ember", "emerald", "engine", "envelope",
    "fabric", "falcon", "feather", "fiddle", "freckle", "gadget",
    "galaxy", "garden", "ginger", "giraffe", "glacier", "goblet",
    "guitar", "harvest", "honey", "horizon", "hotel", "igloo",
    "indigo", "insect", "jaguar", "jigsaw", "jungle", "kayak",
    "kingdom", "kitchen", "koala", "ladder", "lagoon", "lantern",
    "lavender", "library", "lizard", "lumber", "maple", "marble",
    "meadow", "mirror", "monkey", "mountain", "muffin", "napkin",
    "narrow", "nectar", "nephew", "noodle", "nutmeg", "oasis",
    "ocean", "olive", "onion", "orange", "orchid", "otter",
    "outfit", "oyster", "paddle", "pebble", "pencil", "penguin",
    "pillow", "planet", "pocket", "pumpkin", "puzzle", "quarry",
    "quiver", "radish", "rainbow", "ribbon", "river", "sandal",
    "shadow", "silver", "spider", "squirrel", "sunset", "sweater",
    "table", "teapot", "thunder", "ticket", "tractor", "trumpet",
    "turtle", "umbrella", "unicorn", "upstairs", "utensil", "vanilla",
    "velvet", "village", "vinegar", "violin", "volcano", "waffle",
    "wagon", "walnut", "walrus", "window", "yellow", "yogurt",
    "zebra", "zenith", "zipper", "zucchini",
]


if __name__ == "__main__":
    words = build_vocabulary()
    print(f"# {len(words)} words, first letters: {''.join(sorted({w[0] for w in words}))}")
    print("CHALLENGE_VOCABULARY = [")
    for i in range(0, len(words), 6):
        print("    " + ", ".join(f'"{w}"' for w in words[i:i + 6]) + ",")
    print("]")
