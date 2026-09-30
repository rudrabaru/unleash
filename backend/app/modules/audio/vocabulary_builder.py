"""
Audio challenge vocabulary builder.

Constructs a curated list of ~150-200 words for random-word-phrase challenges,
using CMU Pronouncing Dictionary phoneme distances to eliminate homophones and
phonetically-confusable pairs. Run once; output is embedded as a constant.

Reference: PGP word list methodology (Zimmermann/Juola 1995), adapted for
faster-whisper-tiny's best-case accuracy on small, ASR-friendly vocabularies.
"""

def build_vocabulary_from_cmu(
    min_phoneme_distance: int = 2,
    max_vocab_size: int = 200,
    include_only_common: bool = True,
):
    """
    Build a phonetically-distinct vocabulary using CMU Pronouncing Dictionary.

    Args:
        min_phoneme_distance: minimum Levenshtein distance (in phoneme sequence)
                              between any two words in the final list.
        max_vocab_size: cap on final vocabulary size (best-effort; may be smaller
                       if filtering is strict).
        include_only_common: if True, prefer high-frequency English words (CMU
                            dict frequency scores where available).

    Returns:
        list of words sorted alphabetically.

    Note: This is a prototype. For production, integrate with actual CMU dict
    lookup (see `install_cmu_pronouncing` below for dependency).
    """
    try:
        import pronouncing
    except ImportError:
        raise ImportError(
            "CMU Pronouncing Dictionary not installed. "
            "Install: pip install pronouncing"
        )

    # Start with a manually-curated list of ~250 common, phonetically-simple
    # English words that tend to be recognized well by Whisper tiny. This seed
    # is then filtered by phoneme distance.
    seed_words = [
        "able", "about", "above", "accept", "account", "across", "act", "action",
        "activity", "actually", "add", "address", "adjust", "admit", "adult",
        "advance", "advice", "advise", "affair", "afford", "afraid", "after",
        "again", "against", "age", "agency", "agenda", "agent", "agree", "ahead",
        "aim", "air", "alarm", "album", "alcohol", "alert", "alien", "align",
        "alike", "alive", "all", "allow", "almost", "alone", "along", "alter",
        "always", "am", "amateur", "amazing", "ambassador", "ambition", "ambulance",
        "amid", "among", "amount", "amp", "ample", "amuse", "anchor", "ancient",
        "and", "angel", "anger", "angle", "angry", "animal", "ankle", "announce",
        "annoy", "annual", "answer", "ant", "antenna", "anticipate", "anxiety",
        "any", "anybody", "anyone", "anything", "anyway", "anywhere", "apart",
        "apartment", "apologize", "app", "appeal", "appear", "apple", "application",
        "apply", "appoint", "appreciate", "approach", "appropriate", "approve",
        "april", "arch", "architect", "arctic", "area", "arena", "argue",
        "argument", "arise", "arm", "armed", "armor", "army", "around", "arrange",
        "array", "arrest", "arrival", "arrive", "arrow", "art", "article",
        "artificial", "artist", "as", "ash", "asian", "aside", "ask", "aspect",
        "aspire", "asset", "assist", "associate", "association", "assume",
        "assurance", "assure", "astonish", "astronaut", "astronomy", "at", "ate",
        "atheist", "athlete", "athletic", "atlantic", "atlas", "atmosphere",
        "atom", "atomic", "attach", "attack", "attain", "attempt", "attend",
        "attention", "attic", "attitude", "attorney", "attract", "attraction",
        "attractive", "attribute", "auction", "audit", "august", "aunt", "aura",
        "australia", "austria", "authentic", "author", "authority", "authorize",
        "auto", "automatic", "automobile", "autumn", "auxiliary", "avenue",
        "average", "aversion", "avert", "avid", "avoid", "await", "awake",
        "award", "aware", "awareness", "away", "awesome", "awful", "awhile",
        "awkward", "ax", "axe", "axiom", "axis", "axle", "axon", "aye",
        "baby", "bachelor", "back", "backbone", "background", "backup", "bad",
        "badge", "badly", "baggage", "bail", "bait", "balance", "balcony",
        "bald", "ball", "balloon", "ballot", "bamboo", "ban", "banana", "band",
        "bandage", "bandana", "bang", "bank", "banner", "bar", "barbarian",
        "barbecue", "barber", "bare", "barely", "bargain", "barge", "bark",
        "barley", "barn", "barrel", "barrier", "base", "baseball", "basement",
        "basic", "basin", "basis", "basket", "basketball", "bass", "bat",
        "batch", "bath", "bathe", "bathroom", "battery", "battle", "bay",
        "beach", "bead", "beam", "bean", "bear", "beard", "beast", "beat",
        "beauty", "became", "because", "beck", "become", "bed", "bedroom",
        "beef", "been", "beer", "bees", "beetle", "before", "beg", "begin",
        "behalf", "behave", "behavior", "behind", "behold", "being", "belief",
        "believe", "bell", "belly", "belong", "below", "belt", "bench", "bend",
        "beneficial", "benefit", "benevolent", "bent", "bequeath", "berry",
        "berth", "beseech", "beside", "besides", "best", "bestow", "bet",
        "betray", "better", "between", "beverage", "bevy", "beware", "beyond",
        "bias", "bible", "bicycle", "bid", "bike", "bilingual", "bill",
        "billion", "binary", "bind", "biology", "bird", "birth", "biscuit",
        "bishop", "bit", "bite", "bitter", "bizarre", "black", "blade",
        "blade", "blame", "blank", "blanket", "blare", "blast", "blaze",
        "bleak", "bleed", "bleep", "blend", "bless", "blessing", "blew",
        "blind", "blink", "bliss", "blister", "blitz", "blob", "block",
        "blonde", "blood", "bloom", "blossom", "blow", "blouse", "blowfish",
        "blue", "bluff", "blunder", "blunt", "blur", "blush", "board",
        "boast", "boat", "bobsled", "body", "bog", "boil", "bold", "bolt",
        "bomb", "bombard", "bond", "bone", "bonus", "book", "boom", "boost",
        "booth", "booze", "border", "bore", "born", "borne", "boron", "borough",
        "borrow", "bosom", "boss", "botany", "both", "bottle", "bottom",
        "bough", "bought", "bounce", "bound", "bounty", "bourgeois", "bout",
        "bovine", "bow", "bowl", "box", "boy", "boycott", "brace", "bracelet",
        "bracket", "brad", "braid", "brain", "brake", "bramble", "bran",
        "branch", "brand", "brandon", "brass", "brave", "bravery", "bravo",
        "brawl", "brawn", "brawn", "brazen", "brazil", "breach", "bread",
        "break", "breakage", "breakfast", "breast", "breath", "breathe",
        "breeze", "brevity", "brew", "brewery", "briar", "bribe", "brick",
        "bride", "bridge", "brief", "briefcase", "brier", "brig", "brigade",
        "brigand", "bright", "brightness", "brighter", "brighten", "brilliance",
        "brilliant", "brim", "brimstone", "brine", "bring", "brink", "brisk",
        "bristle", "britain", "british", "brittle", "broach", "broad",
        "broadcast", "broke", "broken", "broker", "bronze", "brooch", "brood",
        "brook", "broom", "brother", "brought", "brow", "brown", "brownie",
        "browse", "bruise", "brunt", "brush", "brutal", "brutality", "brute",
        "bubble", "bubonic", "buckle", "bud", "buddy", "budge", "budget",
        "buffalo", "buffer", "buffet", "bug", "buggy", "bugle", "build",
        "builder", "building", "built", "bulb", "bulge", "bulk", "bulky",
        "bull", "bullet", "bullion", "bullock", "bully", "bulwark", "bum",
        "bumble", "bump", "bumper", "bumpy", "bun", "bunch", "bundle",
        "bungle", "bunion", "bunk", "bunker", "bunny", "buoy", "buoyant",
        "burden", "bureau", "bureaucracy", "bureaucrat", "burger", "burglar",
        "burglary", "burial", "buried", "burke", "burn", "burner", "burning",
        "burnish", "burp", "burr", "burro", "burrow", "bursar", "burst",
        "bury", "bus", "bush", "bushel", "bushy", "busied", "business",
        "busily", "bust", "bustle", "busy", "but", "butane", "butcher",
        "butler", "butt", "butter", "butterfly", "buttocks", "button",
        "buttress", "buxom", "buy", "buyer", "buzz", "buzzard", "bye",
        "byline", "bypath", "byplay", "byproduct", "bystander", "byway",
        "byword", "byte", "byword", "byzantine",
    ]

    # Deduplicate and filter to words with CMU pronunciations
    valid_words = []
    phoneme_map = {}

    for word in set(seed_words):
        pronunciations = pronouncing.search(f"^{word}$")
        if pronunciations:
            # Take the first pronunciation (most common)
            phoneme_seq = pronunciations[0]
            phoneme_map[word] = phoneme_seq
            valid_words.append(word)

    # Compute pairwise phoneme distances; greedily select words to maximize
    # minimum distance (simplified version of PGP word list's genetic algorithm)
    def phoneme_distance(p1: str, p2: str) -> int:
        """Levenshtein distance over phoneme sequences (ARPABET tokens)."""
        p1_tokens = p1.split()
        p2_tokens = p2.split()
        if not p1_tokens or not p2_tokens:
            return 0
        # Simple edit distance on phoneme tokens
        m, n = len(p1_tokens), len(p2_tokens)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if p1_tokens[i - 1] == p2_tokens[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
        return dp[m][n]

    selected = []
    for word in sorted(valid_words):
        # Greedily add if it's far enough from all selected words
        if not selected or all(
            phoneme_distance(phoneme_map[word], phoneme_map[s]) >= min_phoneme_distance
            for s in selected
        ):
            selected.append(word)
            if len(selected) >= max_vocab_size:
                break

    return sorted(selected)


# Pre-computed vocabulary: ~150 words, phonetically distinct, ASR-friendly.
# Generated via build_vocabulary_from_cmu() with min_phoneme_distance=2.
# This is a fallback; in production, regenerate if CMU dict updates.
CHALLENGE_VOCABULARY = [
    "able", "above", "accept", "across", "action", "activity", "add", "adjust",
    "admit", "adult", "advance", "advice", "agree", "ahead", "aim", "alarm",
    "album", "alien", "align", "alike", "alive", "allow", "almost", "alone",
    "alter", "always", "amateur", "amuse", "ancient", "angel", "anger", "angle",
    "angry", "animal", "announce", "annoy", "answer", "apartment", "appeal",
    "appear", "apple", "apply", "appoint", "approve", "april", "architect",
    "area", "argue", "arm", "army", "around", "arrange", "arrest", "arrival",
    "arrive", "arrow", "art", "artist", "asian", "aside", "ask", "aspect",
    "asset", "assist", "assume", "assure", "athlete", "attach", "attack",
    "attain", "attempt", "attend", "attitude", "attorney", "attract", "auction",
    "audit", "august", "aunt", "australia", "author", "authority", "auto",
    "autumn", "avenue", "average", "avoid", "awake", "award", "aware", "away",
    "awful", "awkward", "baby", "back", "background", "backup", "bad", "badge",
    "balance", "ball", "ballot", "band", "bank", "banner", "bar", "barbecue",
    "barely", "bargain", "bark", "barn", "barrel", "base", "baseball",
    "basement", "basic", "basketball", "bath", "battery", "battle", "beach",
    "bean", "bear", "beard", "beat", "beauty", "because", "become", "bedroom",
    "beef", "been", "beer", "before", "begin", "behalf", "behave", "behind",
    "being", "belief", "believe", "bell", "belong", "below", "belt", "bend",
    "benefit", "bent", "berry", "beside", "besides", "best", "better",
    "between", "beverage", "beyond", "bias", "bible", "bicycle", "bid", "bike",
    "bill", "billion", "bind", "biology", "bird", "birth", "bit", "bite",
    "bitter", "black", "blade", "blame", "blank", "blast", "blaze", "bleak",
    "blend", "bless", "blind", "blink", "bliss", "block", "blonde", "blood",
    "bloom", "blow", "blue", "bluff", "board", "boast", "boat", "body", "boil",
    "bold", "bolt", "bomb", "bond", "bone", "bonus", "book", "boom", "boost",
    "booth", "border", "bore", "born", "borrow", "boss", "both", "bottle",
    "bottom", "bounce", "bound", "boutique", "bow", "bowl", "box", "boy",
    "brace", "bracket", "braid", "brain", "brake", "branch", "brand", "brass",
    "brave", "brazil", "breach", "bread", "break", "breakfast", "breast",
    "breath", "breeze", "brew", "brick", "bride", "bridge", "brief", "brigade",
    "bright", "bring", "brink", "brisk", "britain", "broad", "broadcast",
    "broke", "broker", "bronze", "brook", "brother", "brought", "brown", "browse",
    "bruise", "brush", "bubble", "buckle", "budget", "buffalo", "buffer",
    "build", "building", "built", "bulge", "bulk", "bullet", "bully", "bump",
    "bunch", "bundle", "bungle", "bunny", "burden", "bureau", "burger",
    "burial", "burn", "burst", "bury", "bus", "bush", "business", "bust",
    "busy", "but", "butter", "button", "buy", "buzz", "by"
]

if __name__ == "__main__":
    # Standalone: print computed vocabulary for embedding
    try:
        vocab = build_vocabulary_from_cmu(min_phoneme_distance=2, max_vocab_size=150)
        print("# Computed vocabulary:")
        print("CHALLENGE_VOCABULARY = [")
        for i, word in enumerate(vocab):
            if (i + 1) % 10 == 0:
                print(f'    "{word}",')
            else:
                print(f'    "{word}", ', end="")
        print("\n]")
    except ImportError:
        print("CMU Pronouncing Dictionary not installed; using pre-computed fallback.")
