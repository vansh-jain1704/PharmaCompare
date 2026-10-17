"""
Ranking for the manual "which medicine is this?" picker.

This is a SEARCH, driven by a person typing; it is never used to settle a prescription line. It makes no
fuzzy guesses: a word either appears in a product (as a whole word, a word prefix, or a strength) or it does
not, and the result is deterministic. Whatever the person picks is still saved only when they press Confirm.

What it fixes in the old LIKE-based search:
  - "Pan D", "Pan-D" and "pan - D" are the same query (hyphens, dots and spaces all separate words), and
    "T. pan-D" / "Tab Pan-D" read the leading T / Tab as "tablet", exactly as the matcher does;
  - every word of the query has to match (name, ingredients, strength or release type), so
    "calcium carbonate vitamin d3" and "Metformin 500 SR" find the products they describe;
  - results are ranked by relevance (whole words beat prefixes beat substrings, the brand beats a look-alike
    like "Span D" or "Pany D") instead of by name length;
  - a number matches a strength, never part of one ("5" is not "500"), "60 k" means 60K, and a release marker
    (SR/ER/XR/CR/PR) means that release type.
"""
import re

_WORD_RE = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
_UNIT_GLUE_RE = re.compile(r"(\d)\s+(k|mg|mcg|gm|g|ml|iu)\b")
_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{3}\b)")
_NUMERIC_RE = re.compile(r"^\d+(?:\.\d+)?k?$")
_NUMBER_WITH_UNIT_RE = re.compile(r"^(\d+(?:\.\d+)?)(k|mg|mcg|gm|g|ml|iu|%)?$")

# words that describe the dosage form: a hint for ranking, never a word the product has to contain
FORM_WORDS = {
    "tab": "tablet", "tabs": "tablet", "tablet": "tablet", "tablets": "tablet",
    "cap": "capsule", "caps": "capsule", "capsule": "capsule", "capsules": "capsule",
    "syp": "syrup", "syr": "syrup", "syrup": "syrup", "susp": "suspension", "suspension": "suspension",
    "inj": "injection", "injection": "injection", "oint": "ointment", "ointment": "ointment",
    "cream": "cream", "gel": "gel", "drops": "drops", "drop": "drops", "lotion": "lotion",
}
# a release marker the person typed -> the release_type stored on products (see release_type.py)
RELEASE_WORDS = {"sr": "sr", "er": "er", "xr": "er", "xl": "er", "cr": "cr", "pr": "pr", "retard": "sr", "dt": "dt", "odt": "odt"}

DISCONTINUED_PENALTY = 50.0

# how well one query word matched one product (higher is better)
EXACT_NAME, EXACT_COMPOSITION, PREFIX_NAME, PREFIX_COMPOSITION, SUBSTRING_NAME, SUBSTRING_COMPOSITION = 4.0, 3.0, 2.5, 2.0, 1.0, 0.5


def words(text):
    return _WORD_RE.findall((text or "").lower())


def parse_query(term):
    """
    {"tokens": [...], "form_hint": str|None, "release_hints": {...}} for what the person typed.
    Hyphens, dots, slashes and extra spaces all just separate words.
    """
    text = _THOUSANDS_RE.sub("", (term or "").lower())            # "60,000" -> "60000"
    text = _UNIT_GLUE_RE.sub(r"\1\2", text)                       # "60 k" -> "60k", "500 mg" -> "500mg"
    found = words(text)
    form_hint = None
    if len(found) > 1 and found[0] == "t":                        # a leading "T." is how doctors write tablet
        form_hint, found = "tablet", found[1:]
    tokens, release_hints = [], {}
    for word in found:
        if word in FORM_WORDS:
            form_hint = form_hint or FORM_WORDS[word]
            continue
        if word in RELEASE_WORDS:
            release_hints[word] = RELEASE_WORDS[word]
        tokens.append(word)
    return {"tokens": tokens, "form_hint": form_hint, "release_hints": release_hints}


def alternatives(token):
    """The spellings of one query word that count as the same word: "60k" is also 60000."""
    alts = [token]
    match = re.match(r"^(\d+)k$", token)
    if match:
        alts.append(str(int(match.group(1)) * 1000))
    return alts


def _number_matches(token, word):
    """A number matches a strength word: equal, or equal with a unit glued on ("500" ~ "500mg"). Never a part of one."""
    t, w = _NUMBER_WITH_UNIT_RE.match(token), _NUMBER_WITH_UNIT_RE.match(word)
    if not t or not w:
        return False
    if t.group(2):                      # the query carried its own unit: it has to be the same word
        return token == word
    return t.group(1) == w.group(1)


def _token_level(token, name_words, comp_words, name_lower, comp_lower, release_type):
    """Best match level of one query word against one product, or None if it does not match at all."""
    best = None

    def take(level):
        nonlocal best
        if best is None or level > best:
            best = level

    for alt in alternatives(token):
        numeric = bool(_NUMERIC_RE.match(alt))
        if numeric:
            if any(_number_matches(alt, w) for w in name_words):
                take(EXACT_NAME)
            if any(_number_matches(alt, w) for w in comp_words):
                take(EXACT_COMPOSITION)
            continue
        if alt in name_words:
            take(EXACT_NAME)
        if alt in comp_words:
            take(EXACT_COMPOSITION)
        if len(alt) >= 3:                                         # prefixes and substrings only for real words
            if any(w.startswith(alt) for w in name_words):
                take(PREFIX_NAME)
            if any(w.startswith(alt) for w in comp_words):
                take(PREFIX_COMPOSITION)
            if len(alt) >= 4:
                if alt in name_lower:
                    take(SUBSTRING_NAME)
                if alt in comp_lower:
                    take(SUBSTRING_COMPOSITION)
    if token in RELEASE_WORDS and release_type == RELEASE_WORDS[token]:
        take(EXACT_COMPOSITION)
    return best


def score_row(parsed, row):
    """A relevance score for one product, or None when the product does not match every word typed."""
    name_words = words(row.get("medicine_name"))
    comp_words = words(row.get("composition"))
    name_lower = (row.get("medicine_name") or "").lower()
    comp_lower = (row.get("composition") or "").lower()
    release_type = row.get("release_type")

    levels = []
    for token in parsed["tokens"]:
        level = _token_level(token, name_words, comp_words, name_lower, comp_lower, release_type)
        if level is None:
            return None
        levels.append(level)
    if not levels:
        return None

    score = sum(levels)
    if all(level == EXACT_NAME for level in levels):
        score += 6.0                                               # every word is a whole word of the name
    if name_words and parsed["tokens"] and name_words[0] == parsed["tokens"][0]:
        score += 4.0                                               # it starts like the brand that was typed
    ignorable = set(FORM_WORDS) | set(RELEASE_WORDS)
    core = [w for w in name_words if w not in ignorable]
    typed_core = [t for t in parsed["tokens"] if t not in ignorable]
    if core and core == typed_core:
        score += 3.0                                               # the name IS what was typed (apart from form / release words)

    # A combination product the person did not ask for ranks below the single-ingredient one: typing "Metformin 500"
    # means metformin, not metformin + glimepiride. (Only a ranking preference: the combination is still listed.)
    parts = [p for p in re.split(r"\s*\+\s*", comp_lower) if p.strip()]
    if len(parts) > 1:
        asked = sum(1 for p in parts if any(t in words(p) for t in parsed["tokens"] if not _NUMERIC_RE.match(t)))
        if asked:
            score -= 2.0 * (len(parts) - asked)

    form = (row.get("form") or "").lower()
    if parsed["form_hint"]:
        score += 2.0 if parsed["form_hint"].rstrip("s") in form else -1.0
    if not parsed["release_hints"] and release_type is None:
        score += 1.5                                               # nothing said about release: the ordinary product comes first
    if row.get("composition_incomplete"):
        score -= 2.0
    if row.get("is_discontinued"):
        score -= DISCONTINUED_PENALTY                              # still listed (and tagged), but never ahead of a live product
    return score


def rank_rows(term, rows, limit=20):
    """The rows that match every word typed, best first. Deterministic: ties go to the shorter name, then the name, then the id."""
    parsed = parse_query(term)
    scored = []
    for row in rows:
        score = score_row(parsed, row)
        if score is not None:
            scored.append((-score, len(row.get("medicine_name") or ""), (row.get("medicine_name") or "").lower(), row.get("medicine_id") or 0, row))
    scored.sort(key=lambda item: item[:4])
    return [item[4] for item in scored[:limit]]
