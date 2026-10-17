"""
Allergy check: compares a user's self-declared allergies with the active
ingredients of a medicine.

What this IS: a name match. If the user wrote "aspirin" and the medicine's
recorded salts include aspirin, it flags it. For three common GROUPS people
actually declare (penicillin, sulfa, NSAIDs) it also knows which salts belong
to the group, because a plain substring match would otherwise tell someone
allergic to "penicillin" that amoxycillin - a penicillin - is fine.

What this is NOT: clinical advice or a complete cross-reactivity engine. No
match does not mean safe - it means nothing on file matched what was typed.
The text shown to the user says so, and always sends them to a doctor.

Kept free of any database or other-service imports so it can be used from the
clinical engine and the per-medicine annotation without a circular import.
"""
import re

# Spelling variants -> the spelling the medicines dataset uses.
SPELLING_ALIASES = {
    "amoxicillin": "amoxycillin",
    "acetaminophen": "paracetamol",
    "sulpha": "sulfa",
    "sulphonamide": "sulfonamide",
    "sulphamethoxazole": "sulfamethoxazole",
    "acetylsalicylic acid": "aspirin",
}

# Group name as a user might type it -> the salts that belong to it.
ALLERGY_GROUPS = {
    "penicillin": {
        "aliases": ("penicillin",),
        "members": (
            "penicillin", "amoxycillin", "ampicillin", "cloxacillin", "dicloxacillin",
            "flucloxacillin", "oxacillin", "piperacillin", "benzathine", "benzylpenicillin",
            "phenoxymethylpenicillin", "ticarcillin", "carbenicillin", "nafcillin",
        ),
    },
    "sulfa": {
        "aliases": ("sulfa", "sulfonamide"),
        "members": (
            "sulfa", "sulfamethoxazole", "sulfadiazine", "sulfasalazine", "sulfacetamide",
            "sulfadoxine", "cotrimoxazole", "co-trimoxazole", "sulfonamide",
        ),
    },
    "nsaid": {
        "aliases": ("nsaid", "anti-inflammatory", "anti inflammatory"),
        "members": (
            "ibuprofen", "diclofenac", "aceclofenac", "naproxen", "aspirin", "ketorolac",
            "piroxicam", "meloxicam", "nimesulide", "etoricoxib", "celecoxib", "indomethacin",
            "mefenamic", "flurbiprofen", "ketoprofen", "dexketoprofen", "etodolac",
            "nabumetone", "lornoxicam", "parecoxib", "tenoxicam", "diflunisal",
        ),
    },
}

MIN_TERM_LENGTH = 3
MIN_SALT_WORD = 5


def _norm(text):
    lowered = (text or "").lower().strip()
    for old, new in SPELLING_ALIASES.items():
        lowered = lowered.replace(old, new)
    return re.sub(r"\s+", " ", lowered)


def _salt_text(medicine):
    parts = [medicine.get("primary_salt"), medicine.get("secondary_salt"), medicine.get("composition")]
    return _norm(" ".join(p for p in parts if p))


def _display_salt(medicine, matched_word):
    """The salt as the dataset names it, for the message shown to the user."""
    for key in ("primary_salt", "secondary_salt"):
        value = medicine.get(key)
        if value and matched_word in _norm(value):
            return value.strip()
    return matched_word.title()


def check_medicine_against_allergies(medicine, allergies):
    """
    Returns None, or {"allergy": <what the user typed>, "salt": <dataset salt>,
    "via_group": bool, "text": <message>} for the FIRST allergy that matches.
    """
    if not medicine or not allergies:
        return None
    salts = _salt_text(medicine)
    if not salts:
        return None
    salt_words = [w for w in re.findall(r"[a-z\-]+", salts) if len(w) >= MIN_SALT_WORD]

    for declared in allergies:
        term = _norm(declared)
        if len(term) < MIN_TERM_LENGTH:
            continue

        # 1. Direct name match, either way round ("aspirin" in the salts, or
        #    a salt named inside what the user typed: "aspirin - rash").
        direct = term if term in salts else next((w for w in salt_words if w in term), None)
        if direct:
            return _alert(declared, _display_salt(medicine, direct), via_group=False)

        # 2. Group match ("penicillin" -> amoxycillin).
        for group in ALLERGY_GROUPS.values():
            if any(alias in term for alias in group["aliases"]):
                member = next((m for m in group["members"] if m in salts), None)
                if member:
                    return _alert(declared, _display_salt(medicine, member), via_group=True)
    return None


def _alert(declared, salt, via_group):
    belongs = ", which belongs to that group" if via_group else ""
    return {
        "allergy": declared,
        "salt": salt,
        "via_group": via_group,
        "text": (
            f"You reported an allergy to {declared}. This medicine contains {salt}{belongs}. "
            "Consult your doctor before use."
        ),
    }
