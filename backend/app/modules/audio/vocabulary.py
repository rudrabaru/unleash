"""
The word pool the 5-word verbal challenge is drawn from (`POST /sessions`).

Why a curated pool: challenge entropy is what resists replay and scripted attacks, and a small
vocabulary of acoustically distinct words keeps the speech recognizer near its best accuracy.
The pool was generated once from the CMU Pronouncing Dictionary and committed as this constant:
every word has no homophone anywhere in that dictionary, at least two syllables, is not a
number word (Whisper may transcribe those as digits) or unsuitable to show a user, differs from
every other word by at least 2 phonemes, and is spelled differently enough (similarity < 0.7)
that the phrase check can never confuse two pool words. The generator is not kept: the planned
common-word challenge will need a new pool built from scratch (it is in git history at tag
`pre-solo-reset`). `tests/test_challenge_vocabulary.py` checks the properties that matter.
"""
from typing import List

# 136 words covering 25 letters.
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

