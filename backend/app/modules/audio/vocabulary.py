"""
The word pool the 5-word verbal challenge is drawn from (`POST /sessions`).

Why a curated pool: a person says the words with nothing around them, so the speech recognizer has
no sentence to lean on, and rare nouns are exactly what it hears worst ("lantern" became "Lenton").
This pool holds 156 common, everyday (5-9 letters, 2-3 syllables) words, chosen by
`tools/build_vocabulary.py` from wordfreq, the CMU Pronouncing Dictionary and WordNet. Each word is a
thing most people know at a glance, has no homophone anywhere in the CMU Pronouncing Dictionary, is not
a number word or on the tool's blocklist, differs from every other word by at least 2 phonemes and is
spelled differently enough (similarity under 0.7) that the phrase check can never take one pool word
for another. 187 candidates were spoken by four Windows voices (two US, two Indian-English), with
and without pauses between the words, through the real phrase check; only words heard in at least 3 of
4 trials in both styles were kept. That screen is a proxy (clean synthetic speech): the human pilot
recordings decide whether the pool or the recognizer needs more. The properties are checked by
`tests/test_challenge_vocabulary.py`; the evidence is `eval/vocabulary_screening.json`.
Entropy: 5 words in order from 156 are 36.4 bits, enough against a pre-recorded phrase. It is not what
stops a live synthetic voice (the words are on screen for 8 s); the challenge protocol does that work.
"""
from typing import List

# 156 words covering 22 letters.
CHALLENGE_VOCABULARY: List[str] = [
    "aircraft", "airplane", "airport", "apartment", "attic", "backyard",
    "balloon", "banana", "banner", "basement", "basket", "bathroom",
    "bedroom", "bicycle", "bottle", "breakfast", "bucket", "buffalo",
    "butter", "button", "cabinet", "candle", "candy", "canyon",
    "cargo", "carpet", "carriage", "cattle", "chamber", "chicken",
    "chimney", "chocolate", "classroom", "closet", "cockpit", "collar",
    "compass", "costume", "cottage", "curtain", "daisy", "dinner",
    "doorway", "driveway", "eagle", "elephant", "engine", "entrance",
    "envelope", "fabric", "factory", "falcon", "feather", "fireplace",
    "freeway", "furniture", "garage", "garden", "gateway", "glacier",
    "grocery", "highway", "honey", "hospital", "hotel", "insect",
    "island", "jacket", "jelly", "keyboard", "kitchen", "ladder",
    "laundry", "linen", "lizard", "lobby", "locker", "luggage",
    "machine", "makeup", "maple", "marker", "monkey", "monument",
    "mosaic", "mosquito", "motor", "mountain", "museum", "necklace",
    "needle", "nursery", "ocean", "office", "orchard", "oyster",
    "panther", "parachute", "pencil", "photo", "picture", "pigeon",
    "pillow", "pizza", "planet", "platform", "pocket", "pottery",
    "puppy", "rabbit", "railroad", "railway", "rainbow", "rhino",
    "ribbon", "river", "saddle", "satellite", "sausage", "sculpture",
    "sedan", "shelter", "shipment", "sidewalk", "spider", "staircase",
    "staple", "station", "statue", "studio", "submarine", "subway",
    "suitcase", "supper", "tablet", "temple", "terminal", "tomato",
    "tower", "tractor", "turbine", "turkey", "umbrella", "uniform",
    "vegetable", "vehicle", "velvet", "vinegar", "violet", "volcano",
    "wagon", "wardrobe", "warehouse", "waterfall", "window", "workshop",
]
