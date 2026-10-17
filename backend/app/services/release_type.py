"""
Release type: the one thing the Medicines table does not store as a column
but that decides whether two tablets are the same medicine.

A "Metformin 500mg Tablet" taken twice a day and a "Metformin 500mg Tablet SR"
(sustained release) are not interchangeable, yet in the imported dataset both
have form = "Tablet". The release mechanism only appears as text: at the end of
pack_size ("strip of 10 tablet sr") and/or as a word in the name
("Allmet 500mg Tablet SR"). The two fields also disagree with each other at
times, so the derivation below is deliberately conservative.

Values (NULL means "no modified-release marker found", i.e. conventional):
    sr        sustained release
    er        extended release (ER, XR, XL are the same convention)
    cr        controlled release
    pr        prolonged release
    mr        modified release (only trusted when pack_size says so; in a brand
              name "MR" is often "muscle relaxant")
    dt        dispersible tablet
    odt       mouth-dissolving / orally disintegrating
    chewable  chewable
    ec        enteric coated / gastro-resistant
    modified  pack_size and name name DIFFERENT mechanisms, so we only know
              that it is not conventional

    "Retard" (nifedipine retard, carbamazepine retard) is sustained release and "Chrono"
    (sodium valproate chrono) is a modified-release valproate; both are unambiguous.

Not treated as release markers, because the dataset shows they mean other things as well:
"OD" (once daily - a dosing frequency, found in names such as "Addwize OD 18mg Tablet"),
"LA", "TR" (also tranexamic acid combinations), "SA" (also a repaglinide brand) and
"MR" (about 2,000 products, nearly all muscle-relaxant combinations). Being wrong in the
"not a marker" direction is the unsafe one, so each of these was checked against the data
(see database/audit_release_markers.py) before being left out.
"""
import re

CONVENTIONAL = None
MODIFIED_UNKNOWN = "modified"

RELEASE_LABELS = {
    "sr": "sustained release",
    "er": "extended release",
    "cr": "controlled release",
    "pr": "prolonged release",
    "mr": "modified release",
    "dt": "dispersible",
    "odt": "mouth-dissolving",
    "chewable": "chewable",
    "ec": "enteric coated",
    "modified": "modified release",
}

# marker word -> canonical class
_MARKERS = {
    "sr": "sr", "er": "er", "xr": "er", "xl": "er", "cr": "cr", "pr": "pr", "mr": "mr",
    "dt": "dt", "md": "odt", "odt": "odt", "chewable": "chewable", "ec": "ec", "gr": "ec",
    "retard": "sr", "chrono": MODIFIED_UNKNOWN,
}
# In a NAME these are trusted; MR is not (see module docstring).
_NAME_MARKERS = {k for k in _MARKERS if k != "mr"}

_SOLID_FORMS = ("tablet", "capsule", "caplet")

_PACK_TAIL_RE = re.compile(
    r"\b(?:tablets?|capsules?|caplets?)\s+(" + "|".join(sorted(_MARKERS, key=len, reverse=True)) + r")\s*$",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-z]+")

_PHRASES = (
    (re.compile(r"\bsustained[\s-]*release\b", re.IGNORECASE), "sr"),
    (re.compile(r"\bextended[\s-]*release\b", re.IGNORECASE), "er"),
    (re.compile(r"\bcontrolled[\s-]*release\b", re.IGNORECASE), "cr"),
    (re.compile(r"\bprolonged[\s-]*release\b", re.IGNORECASE), "pr"),
    (re.compile(r"\bmodified[\s-]*release\b", re.IGNORECASE), "mr"),
    (re.compile(r"\b(?:dispersible)\b", re.IGNORECASE), "dt"),
    (re.compile(r"\b(?:mouth[\s-]*dissolving|orally[\s-]*disintegrating)\b", re.IGNORECASE), "odt"),
    (re.compile(r"\b(?:enteric[\s-]*coated|gastro[\s-]*resistant)\b", re.IGNORECASE), "ec"),
)


def is_modified(release_type):
    """True for anything that is not a conventional (immediate-release) product."""
    return release_type is not None


def _is_solid_oral(name, pack_size, form):
    haystack = " ".join(x for x in (form, pack_size) if x).lower()
    return any(w in haystack for w in _SOLID_FORMS)


def derive_release_type(name, pack_size, form):
    """
    Release type of one catalogue product, from its pack_size and name.
    Returns one of the values documented at the top, or None.
    """
    pack_class = None
    pack_match = _PACK_TAIL_RE.search((pack_size or "").strip())
    if pack_match:
        pack_class = _MARKERS[pack_match.group(1).lower()]

    name_class = None
    if _is_solid_oral(name, pack_size, form):
        words = _WORD_RE.findall((name or "").lower())
        found = [_MARKERS[w] for w in words if w in _NAME_MARKERS]
        if not found:
            for pattern, canonical in _PHRASES:
                if canonical != "mr" and pattern.search(name or ""):
                    found.append(canonical)
        if found:
            name_class = found[-1]  # the marker conventionally trails the name

    if pack_class and name_class and pack_class != name_class:
        return MODIFIED_UNKNOWN
    return pack_class or name_class


# ---- the prescription line ------------------------------------------------------------

# Markers a prescriber actually writes. "md" is left out (it is also "M.D.", a
# doctor's degree) and so is "mr" (muscle relaxant); a missing marker only
# means the line is treated as not specifying a release type.
_LINE_MARKERS = {"sr": "sr", "er": "er", "xr": "er", "xl": "er", "cr": "cr", "pr": "pr", "dt": "dt", "odt": "odt", "chewable": "chewable",
                 "retard": "sr", "chrono": MODIFIED_UNKNOWN}
_LINE_WORD_RE = re.compile(r"(?<![a-z])(sr|er|xr|xl|cr|pr|dt|odt|chewable|retard|chrono)(?![a-z])", re.IGNORECASE)


def detect_line_release(text):
    """
    The release type a prescription line explicitly states ("Metformin 500 SR",
    "... sustained release"), or None when it states none.
    """
    text = text or ""
    for pattern, canonical in _PHRASES:
        if canonical in ("sr", "er", "cr", "pr", "dt", "odt") and pattern.search(text):
            return canonical
    # "S.R." / "X.L." written with dots
    squashed = re.sub(r"(?<![a-z])([sxecp])\.\s*([rl])\.?(?![a-z])", lambda m: m.group(1) + m.group(2), text, flags=re.IGNORECASE)
    match = _LINE_WORD_RE.search(squashed)
    return _LINE_MARKERS[match.group(1).lower()] if match else None
