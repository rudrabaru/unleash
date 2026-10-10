"""
Build the word pool the 5-word spoken challenge is drawn from.

Three steps, run from backend/ (needs `pip install -r requirements-tools.txt`, plus Windows for the
text-to-speech screen):

  python tools/build_vocabulary.py candidates            # write eval/vocabulary_candidates.json
  python tools/build_vocabulary.py screen --pool candidates   # speak them with 4 voices, check the phrase check hears them
  python tools/build_vocabulary.py screen --pool current      # the same for the live pool, for comparison
  (add --style run_together for the harder case where the voice does not pause between words)
  python tools/build_vocabulary.py write                 # write app/modules/audio/vocabulary.py

Why these rules (the phrase check hears isolated words with no sentence around them, so the words
themselves must be easy):

  * common (wordfreq Zipf frequency of at least 3.5), 5-9 letters and 2-3 syllables (a one-syllable
    word is too little sound for a recogniser with no sentence around it: 71% of trials against
    85% for two syllables in the first screen);
  * an everyday thing as the main meaning (WordNet: animal, artifact, food, plant, natural object),
    a plain base form (not a plural or an -ing form), mostly used as a noun, and not a
    proper noun (WordNet writes those with a capital), so people can read it at a glance;
  * no homophone anywhere in the CMU Pronouncing Dictionary ("pair"/"pear" would be scored by luck);
  * no number words and nothing from the blocklist below;
  * words differ from each other by at least 2 phonemes, and are spelled differently enough that the
    phrase check can never take one pool word for another (similarity under 0.7, the same
    properties as the earlier pool).

The screen speaks random 5-word phrases with Windows voices, two US and two Indian-English, at
different speeds, and runs them through the real phrase check (base.en, the same matcher and
confidence floor). Words recognised in at least 3 of their 4 trials are kept. Text-to-speech is a
proxy: it is clean, steady speech, and it says nothing about accents of real speakers, noise or
fast speech. The screen finds words that fail even then; the human pilot decides the rest.
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import shutil
import subprocess
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("ENVIRONMENT", "development")  # a tool is a development program; the app defaults to production

CANDIDATES_FILE = BACKEND / "eval" / "vocabulary_candidates.json"
SCREENING_FILE = BACKEND / "eval" / "vocabulary_screening.json"
VOCABULARY_FILE = BACKEND / "app" / "modules" / "audio" / "vocabulary.py"

MIN_ZIPF = 3.5
MIN_LETTERS, MAX_LETTERS = 5, 9
# One-syllable words are too little sound to recognise on their own (71% of trials against 85% for
# two syllables in the first screen), and long words are harder to read at a glance.
MIN_SYLLABLES, MAX_SYLLABLES = 2, 3
# Everyday things. Body parts and substances are left out on purpose: they bring anatomy and chemistry
# ("colon", "nitrogen") and words nobody wants to read aloud to a camera.
CONCRETE = {"noun.animal", "noun.artifact", "noun.food", "noun.plant", "noun.object"}
NOUN_SHARE = 0.7  # of the word's uses in WordNet's sense-tagged text, at least this share must be as a noun
MIN_PHONEME_DISTANCE = 2
MAX_SPELLING_SIMILARITY = 0.7  # strictly below the phrase check's 0.8 match line, with room to spare

NUMBER_WORDS = set("one two three four five six seven eight nine ten eleven twelve zero dozen hundred thousand million".split())
# Unsuitable to show a person, or likely to be heard as something else in a short phrase.
BLOCKLIST = set(
    """
    blood bomb breast butt corpse crime death drug drugs drunk gun knife murder nude porn pistol rifle
    sex sexy shot skull slave sperm stab tits war weapon whip wine beer vodka gambling cigar smoke
    bible church god devil hell jesus priest muslim jew gay rape rich poor tax cash loan debt
    penis pussy piss shit sweat flesh toilet prison jail bullet missile virus nerve organ lung
    kidney stomach throat skin crack crude crush cure pills spam trash junk refuse remains casting
    brad chuck trump murphy logan jordan derby delta asia europe costa harvard hudson
    spoke setup output outlet starter holder segment product system portal haven drone vinyl metro
    transit vintage diet weed dust gulf mine facing filling housing landing
    afghan bomber cocaine coffin shotgun urine hormone enzyme serum membrane plasma thigh spine fortress
    trench rubbish mike jeep lance python shrine fraction textile forehead
    alcohol firearm grenade dagger destroyer dungeon sewage sewer underwear casino champagne cigarette
    tobacco nicotine parasite casino cathedral ambulance asphalt maria decor structure solution interface
    diagram assembly partition enclosure residue fragment particle emblem substrate backdrop backstage
    fallout detector receiver recorder timer cleaner builder equipment container continent universe
    cavity colon cortex thyroid insulin artery abdomen calcium mercury molecule electron antenna
    nightclub tavern lipstick embassy algae livestock poultry hardware mainland footage depot junction
    layer barrier scenery agent boiler capsule
    """.split()
)

# (voice, speech rate from -10 slowest to +10 fastest): two US and two Indian-English voices, mixed paces
VOICES: Sequence[Tuple[str, int]] = (
    ("Microsoft David Desktop", 0),
    ("Microsoft Zira Desktop", 1),
    ("Microsoft Ravi", 0),
    ("Microsoft Heera", 2),
)
KEEP_AT_LEAST = 3  # trials (of 4) a word must be recognised in
# "paused": a short pause between words, as a person reading five separate words usually leaves.
# "run_together": no pause, which makes the recognizer glue neighbours into one word ("sugarhead").
STYLES = ("paused", "run_together")
ASK_SCRIPT = r"""
param($jobsPath)
Add-Type -AssemblyName System.Speech
$jobs = Get-Content $jobsPath -Raw | ConvertFrom-Json
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
foreach ($job in $jobs) {
    $speaker.SelectVoice($job.voice)
    $speaker.Rate = [int]$job.rate
    $speaker.SetOutputToWaveFile($job.path)
    $speaker.Speak($job.text)
    $speaker.SetOutputToNull()
}
$speaker.Dispose()
"""


# --- pronunciation helpers ----------------------------------------------------------------------

def _phonemes(pronunciation: Sequence[str]) -> Tuple[str, ...]:
    """A CMU pronunciation without its stress digits."""
    return tuple("".join(ch for ch in p if not ch.isdigit()) for p in pronunciation)


def _syllables(pronunciation: Sequence[str]) -> int:
    return sum(1 for p in pronunciation if p[-1].isdigit())


def phoneme_distance(a: Sequence[str], b: Sequence[str]) -> int:
    """Edit distance between two phoneme sequences."""
    row = list(range(len(b) + 1))
    for i, pa in enumerate(a, 1):
        new = [i]
        for j, pb in enumerate(b, 1):
            new.append(min(row[j] + 1, new[j - 1] + 1, row[j - 1] + (pa != pb)))
        row = new
    return row[-1]


def _homophone_index(pronunciations: Dict[str, list], zipf) -> Dict[Tuple[str, ...], set]:
    """Pronunciation (without stress) -> the real words (Zipf at least 2.5) that sound like it."""
    index: Dict[Tuple[str, ...], set] = {}
    for word, variants in pronunciations.items():
        if word.isalpha() and zipf(word, "en") >= 2.5:
            for variant in variants:
                index.setdefault(_phonemes(variant), set()).add(word)
    return index


# --- step 1: candidates -------------------------------------------------------------------------

def _is_concrete_noun(word: str, wordnet) -> bool:
    """A plain, concrete, mostly-noun word that is not a name (see the module notes)."""
    if wordnet.morphy(word) not in (None, word):
        return False  # an inflected form: a plural, an -ing or -ed word
    synsets = wordnet.synsets(word)
    if not synsets or synsets[0].pos() != "n" or synsets[0].lexname() not in CONCRETE:
        return False
    if word not in {lemma.name() for lemma in synsets[0].lemmas()}:
        return False  # WordNet spells proper nouns with a capital
    uses = [(synset.pos(), lemma.count()) for synset in synsets for lemma in synset.lemmas() if lemma.name() == word]
    total = sum(count for _, count in uses) or 1
    return sum(count for pos, count in uses if pos == "n") >= NOUN_SHARE * total


def build_candidates() -> List[dict]:
    """Common, short, concrete, unambiguous words, most frequent first, mutually distinct."""
    import cmudict
    import wordfreq
    from nltk.corpus import wordnet

    pronunciations = cmudict.dict()
    homophones = _homophone_index(pronunciations, wordfreq.zipf_frequency)
    from app.modules.audio._phrase_align import word_similarity_score

    chosen: List[dict] = []
    for word in wordfreq.top_n_list("en", 30000):
        if not (MIN_LETTERS <= len(word) <= MAX_LETTERS and word.isalpha() and word.islower()):
            continue
        if word.endswith(("s", "ing")) and not word.endswith("ss"):
            continue  # plurals and -ing forms are easily heard as the other form
        if wordfreq.zipf_frequency(word, "en") < MIN_ZIPF or word in NUMBER_WORDS or word in BLOCKLIST:
            continue
        variants = pronunciations.get(word)
        if not variants or any(not MIN_SYLLABLES <= _syllables(v) <= MAX_SYLLABLES for v in variants):
            continue
        if any(len(homophones.get(_phonemes(v), {word})) > 1 for v in variants):
            continue  # another real word sounds the same
        if not _is_concrete_noun(word, wordnet):
            continue
        sounds = [_phonemes(v) for v in variants]  # every accepted pronunciation counts: "cabbage" vs "carriage"
        if any(
            min(phoneme_distance(a, b) for a in sounds for b in c["_phonemes"]) < MIN_PHONEME_DISTANCE
            or word_similarity_score(word, c["word"]) >= MAX_SPELLING_SIMILARITY
            for c in chosen
        ):
            continue
        chosen.append({"word": word, "zipf": round(wordfreq.zipf_frequency(word, "en"), 2), "syllables": _syllables(variants[0]), "_phonemes": sounds})
    return [{k: v for k, v in c.items() if not k.startswith("_")} for c in chosen]


# --- step 2: speak them and see whether the phrase check hears them ----------------------------

def _phrases(words: List[str], seed: int) -> List[List[str]]:
    """Random 5-word phrases that together use every word once (the last one may repeat words to fill up)."""
    rng = random.Random(seed)
    shuffled = words[:]
    rng.shuffle(shuffled)
    while len(shuffled) % 5:
        shuffled.append(rng.choice(words))
    return [shuffled[i:i + 5] for i in range(0, len(shuffled), 5)]


def _speak(jobs: List[dict]) -> None:
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        raise SystemExit("The text-to-speech screen needs Windows PowerShell (System.Speech).")
    with tempfile.TemporaryDirectory() as folder:
        script, listing = Path(folder) / "speak.ps1", Path(folder) / "jobs.json"
        script.write_text(ASK_SCRIPT, encoding="utf-8")
        listing.write_text(json.dumps(jobs), encoding="utf-8")
        subprocess.run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), str(listing)], check=True)


def screen(words: List[str], style: str = "paused", seed: int = 1) -> Dict[str, dict]:
    """Per word: in how many of the four voices the real phrase check recognised it, and what it was heard as."""
    from app.modules.audio._phrase_compliance import run_phrase_compliance

    results: Dict[str, dict] = {w: {"heard": 0, "trials": 0, "misheard": []} for w in words}
    started = time.time()
    with tempfile.TemporaryDirectory() as folder:
        for index, (voice, rate) in enumerate(VOICES):
            phrases = _phrases(words, seed + index)
            joiner = ", " if style == "paused" else " "  # a comma gives the synthetic voice a short pause
            jobs = [{"voice": voice, "rate": rate, "text": joiner.join(p), "path": str(Path(folder) / f"{index}_{n}.wav")} for n, p in enumerate(phrases)]
            _speak(jobs)
            for job, phrase in zip(jobs, phrases):
                result = run_phrase_compliance(job["path"], " ".join(phrase))
                heard = {pair.split(" -> ")[1] for pair in (result.details or {}).get("matched_pairs", [])}
                transcript = (result.details or {}).get("transcript", "")
                for word in set(phrase):
                    results[word]["trials"] += 1
                    results[word]["heard"] += word in heard
                    if word not in heard:
                        results[word]["misheard"].append(f"{voice.split()[-1]}: {transcript}")
            print(f"  {voice}: {len(phrases)} phrases done ({time.time() - started:.0f} s)", flush=True)
    return results


# --- step 3: write the pool ---------------------------------------------------------------------

def render_vocabulary(words: List[str], screened: int, source: str) -> str:
    rows = [", ".join(f'"{w}"' for w in words[i:i + 6]) + "," for i in range(0, len(words), 6)]
    body = "\n".join("    " + row for row in rows)
    letters = len({w[0] for w in words})
    return f'''"""
The word pool the 5-word verbal challenge is drawn from (`POST /sessions`).

Why a curated pool: a person says the words with nothing around them, so the speech recognizer has
no sentence to lean on, and rare nouns are exactly what it hears worst ("lantern" became "Lenton").
This pool holds {len(words)} common, everyday (5-9 letters, 2-3 syllables) words, chosen by
`tools/build_vocabulary.py` from wordfreq, the CMU Pronouncing Dictionary and WordNet. Each word is a
thing most people know at a glance, has no homophone anywhere in the CMU Pronouncing Dictionary, is not
a number word or on the tool's blocklist, differs from every other word by at least 2 phonemes and is
spelled differently enough (similarity under 0.7) that the phrase check can never take one pool word
for another. {screened} candidates were spoken by four Windows voices (two US, two Indian-English), with
and without pauses between the words, through the real phrase check; only words heard in at least 3 of
4 trials in both styles were kept. That screen is a proxy (clean synthetic speech): the human pilot
recordings decide whether the pool or the recognizer needs more. The properties are checked by
`tests/test_challenge_vocabulary.py`; the evidence is `eval/vocabulary_screening.json`.
Entropy: 5 words in order from {len(words)} are {5 * __import__("math").log2(len(words)):.1f} bits, enough against a pre-recorded phrase. It is not what
stops a live synthetic voice (the words are on screen for 8 s); the challenge protocol does that work.
"""
from typing import List

# {len(words)} words covering {letters} letters.
CHALLENGE_VOCABULARY: List[str] = [
{body}
]
'''


# --- command line -------------------------------------------------------------------------------

def _load_pool(name: str) -> List[str]:
    if name == "current":
        from app.modules.audio.vocabulary import CHALLENGE_VOCABULARY

        return list(CHALLENGE_VOCABULARY)
    return [c["word"] for c in json.loads(CANDIDATES_FILE.read_text(encoding="utf-8"))["candidates"]]


def _summary(results: Dict[str, dict]) -> str:
    kept = sum(r["heard"] >= KEEP_AT_LEAST for r in results.values())
    trials = sum(r["trials"] for r in results.values())
    return f"{kept}/{len(results)} words heard in at least {KEEP_AT_LEAST} of 4 trials; {sum(r['heard'] for r in results.values())}/{trials} word-trials recognised"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["candidates", "screen", "write"])
    parser.add_argument("--pool", choices=["candidates", "current"], default="candidates", help="which word list `screen` speaks")
    parser.add_argument("--style", choices=STYLES, default="paused", help="how the voice speaks the five words")
    args = parser.parse_args(argv)

    if args.command == "candidates":
        candidates = build_candidates()
        CANDIDATES_FILE.write_text(json.dumps({"rules": __doc__.split("Why these rules")[1].split("The screen speaks")[0].strip(), "candidates": candidates}, indent=1), encoding="utf-8")
        print(f"{len(candidates)} candidates -> {CANDIDATES_FILE}; first letters covered: {len({c['word'][0] for c in candidates})}")
        return 0

    if args.command == "screen":
        results = screen(_load_pool(args.pool), args.style)
        stored = json.loads(SCREENING_FILE.read_text(encoding="utf-8")) if SCREENING_FILE.exists() else {}
        stored[f"{args.pool}_{args.style}"] = {"voices": [f"{v} (rate {r})" for v, r in VOICES], "keep_at_least": KEEP_AT_LEAST, "summary": _summary(results), "words": results}
        SCREENING_FILE.write_text(json.dumps(stored, indent=1), encoding="utf-8")
        print(_summary(results))
        return 0

    # A word has to survive both ways of speaking: people who rush the phrase give the recognizer no pauses.
    stored = json.loads(SCREENING_FILE.read_text(encoding="utf-8"))
    screens = [stored[f"candidates_{style}"]["words"] for style in STYLES]
    candidates = _load_pool("candidates")
    unscreened = [w for w in candidates if any(w not in screen_words for screen_words in screens)]
    if unscreened:
        raise SystemExit(f"Screen these candidates first (both styles): {', '.join(unscreened)}")
    keep = [w for w in candidates if all(screen_words[w]["heard"] >= KEEP_AT_LEAST for screen_words in screens)]
    VOCABULARY_FILE.write_text(render_vocabulary(sorted(keep), len(candidates), "wordfreq, the CMU Pronouncing Dictionary and WordNet"), encoding="utf-8")
    print(f"{len(keep)} words -> {VOCABULARY_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
