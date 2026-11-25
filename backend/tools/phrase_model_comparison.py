"""
Compare speech-recognition setups for the phrase check on recorded takes.

Transcribes every recording once per candidate (model x prompt mode), keeps Whisper's per-word
probabilities, then sweeps the per-word confidence floor *offline* with the real matcher. Use it
to choose the confidence floor once there are enough genuine takes (at least 10, from at least
3 speakers).

Recordings are listed in a manifest (JSON), paths relative to the manifest:
    {"genuine": [{"file": "take1.webm", "speaker": "A", "challenge": "walnut lantern bicycle maple trumpet"}, ...],
     "attacks": [{"file": "wrong_speech.webm", "kind": "wrong speech"}, ...]}
Silence and a tone are always added as attack clips.

For each (candidate, floor):
    genuine : matched/5 against the challenge actually spoken            (false-reject side)
    attacks : % of 2,000 random challenges that reach >= 4/5            (false-accept side)
              Genuine takes are ALSO scored against 2,000 *other* random challenges
              (= replaying a recording of a previous session's phrase).

Usage (from backend/):
    .venv\\Scripts\\python.exe tools/phrase_model_comparison.py tools/phrase_comparison_manifest.json
"""
from __future__ import annotations

import functools
import json
import random
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("ENVIRONMENT", "development")  # a tool is a development program; the app defaults to production

from faster_whisper import WhisperModel  # noqa: E402

from app.modules.audio import _phrase_align as _pa  # noqa: E402
from app.modules.audio._extraction import extract_wav  # noqa: E402
from app.modules.audio._phrase_align import MAX_INSERTED_WORDS, MIN_WORD_SIMILARITY, align_words  # noqa: E402
from app.modules.audio.vocabulary import CHALLENGE_VOCABULARY  # noqa: E402

# Thousands of random-challenge probes repeat the same word pairs; cache the (pure) similarity.
_pa.word_similarity_score = functools.lru_cache(maxsize=None)(_pa.word_similarity_score)

MODELS = ["tiny", "tiny.en", "base.en"]
PROMPT_MODES = ["plain", "prompt"]  # prompt = vocabulary initial_prompt + condition_on_previous_text=False
FLOORS = [0.5, 0.3, 0.2, 0.1]
N_RANDOM_CHALLENGES = 2000
REQUIRED_WORDS = 4  # the phrase check passes at 4 of 5 words
SAMPLE_RATE = 16000


def to_wav(src: Path, tmp: Path) -> Path:
    if src.suffix.lower() == ".wav":
        return src
    out = tmp / f"{src.stem}_16k.wav"
    ok, err, _ = extract_wav(src, out)
    if not ok:
        raise RuntimeError(f"extract failed for {src}: {err}")
    return out


def synthetic_attacks(tmp: Path) -> List[Tuple[Dict[str, str], Path]]:
    """Silence and a 440 Hz tone: non-speech that must never produce challenge words."""
    t = np.linspace(0, 5.0, SAMPLE_RATE * 5, endpoint=False)
    clips = {"silence": np.zeros(SAMPLE_RATE * 5), "tone": 0.5 * np.sin(2 * np.pi * 440 * t)}
    out = []
    for name, data in clips.items():
        path = tmp / f"{name}.wav"
        sf.write(str(path), data.astype(np.float32), SAMPLE_RATE)
        out.append(({"file": path.name, "kind": name}, path))
    return out


def transcribe(model: WhisperModel, wav: Path, mode: str) -> Tuple[List[Tuple[str, float]], float]:
    kwargs: Dict[str, Any] = dict(beam_size=5, language="en", word_timestamps=True,
                                  vad_filter=False, temperature=0.0)
    if mode == "prompt":
        kwargs["initial_prompt"] = ", ".join(CHALLENGE_VOCABULARY)
        kwargs["condition_on_previous_text"] = False
    t0 = time.perf_counter()
    segments, _ = model.transcribe(str(wav), **kwargs)
    words = [(w.word.strip(), w.probability) for s in segments for w in (s.words or []) if w.word.strip()]
    return words, time.perf_counter() - t0


def false_accept_rate(words: List[Tuple[str, float]], floor: float, rng: random.Random) -> float:
    hits = 0
    for _ in range(N_RANDOM_CHALLENGES):
        challenge = rng.sample(CHALLENGE_VOCABULARY, 5)
        found = align_words(words, challenge, min_word_confidence=floor, min_word_similarity=MIN_WORD_SIMILARITY)
        hits += found.match_count >= REQUIRED_WORDS and found.insertions <= MAX_INSERTED_WORDS
    return hits / N_RANDOM_CHALLENGES


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    manifest_path = Path(sys.argv[1])
    manifest = json.loads(manifest_path.read_text())
    base = manifest_path.parent
    tmp = Path(tempfile.mkdtemp(prefix="phrase_comparison_"))

    genuine = [(g, to_wav(base / g["file"], tmp)) for g in manifest["genuine"]]
    attacks = [(a, to_wav(base / a["file"], tmp)) for a in manifest.get("attacks", [])] + synthetic_attacks(tmp)

    for model_name in MODELS:
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        for mode in PROMPT_MODES:
            print(f"\n=== {model_name} / {mode} ===")
            g_tr = [(g, *transcribe(model, wav, mode)) for g, wav in genuine]
            a_tr = [(a, *transcribe(model, wav, mode)) for a, wav in attacks]
            lat = [t for _, _, t in g_tr]
            print(f"genuine latency: mean {sum(lat)/len(lat):.2f}s max {max(lat):.2f}s")
            if len(g_tr) <= 5:
                for g, words, _ in g_tr:
                    print(f"  [{g['speaker']}] {g['file']}: " + " ".join(f"{w}({p:.2f})" for w, p in words))
            for floor in FLOORS:
                rng = random.Random(1)
                counts, missed = [], {}
                for g, words, _ in g_tr:
                    target = g["challenge"].split()
                    found = align_words(words, target, min_word_confidence=floor,
                                        min_word_similarity=MIN_WORD_SIMILARITY)
                    counts.append(found.match_count if found.insertions <= MAX_INSERTED_WORDS else 0)
                    hit = {p.split(" -> ")[1] for p in found.pairs}
                    for t in target:
                        if t not in hit:
                            missed[t] = missed.get(t, 0) + 1
                accepted = sum(c >= REQUIRED_WORDS for c in counts)
                replay = max(false_accept_rate(w, floor, rng) for _, w, _ in g_tr) if g_tr else 0.0
                att = {a["kind"] + ":" + a["file"]: false_accept_rate(w, floor, rng) for a, w, _ in a_tr}
                worst_att = max(att.values()) if att else 0.0
                dist = "" if len(counts) <= 5 else " dist " + str([counts.count(k) for k in range(6)])
                print(f"  floor {floor:.1f}: genuine {accepted}/{len(counts)} pass {counts if len(counts) <= 5 else ''}{dist} | "
                      f"replayed-phrase FAR max {replay:.2%} | non-genuine clips FAR max {worst_att:.2%}")
                if len(counts) > 5 and floor in (0.5, 0.1):
                    top = sorted(missed.items(), key=lambda kv: -kv[1])[:8]
                    print(f"      most-missed target words @ {floor}: {top}")
            for a, words, _ in a_tr:
                print(f"  attack {a['kind']}:{a['file']}: " + (" ".join(f"{w}({p:.2f})" for w, p in words) or "<no words>"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
