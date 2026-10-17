"""
Reading a medicine's active ingredients and their strengths from its
`composition` text, e.g.

    "Amoxycillin  (500mg) + Clavulanic Acid (125 mg)"
    "Telmisartan (40mg) + Hydrochlorothiazide (12.5mg)"
    "Paracetamol (250mg/5ml)"

The Medicines table keeps only the FIRST ingredient's strength in its
`strength` column, so anything that must compare "every active ingredient and
strength" has to read the composition instead.
"""
import re

_STRENGTH_PAIR_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|ug|gm|g|ml|iu|units?|%)", re.IGNORECASE)


def canonical_number(text):
    """'500', '500.0' and '0500' are the same strength; '62.5' stays '62.5'."""
    value = float(text)
    return str(int(value)) if value == int(value) else repr(value)


def split_ingredients(composition):
    """[(name_lowercase, [numbers as canonical strings]), ...] in written order."""
    result = []
    for part in re.split(r"\s*\+\s*", composition or ""):
        part = part.strip()
        if not part:
            continue
        name = re.sub(r"\(.*?\)", "", part).strip().lower()
        name = re.sub(r"\s+", " ", name)
        numbers = [canonical_number(n) for n, _ in _STRENGTH_PAIR_RE.findall(part)]
        result.append((name, numbers))
    return result


def ingredient_numerators(composition):
    """
    One strength per ingredient: the FIRST number in each ingredient's brackets.
    "Paracetamol (250mg/5ml)" gives ['250'] - the "5" is a volume, not a dose, and
    counting it would let a line that merely says "5 ml" agree with any syrup.
    """
    out = []
    for _, numbers in split_ingredients(composition):
        if numbers:
            out.append(numbers[0])
    return out


def ingredient_strengths(composition):
    """Every strength number across every ingredient (per-volume denominators included)."""
    out = []
    for _, numbers in split_ingredients(composition):
        out.extend(numbers)
    return out


def has_unknown_strength(composition):
    """
    True when at least one ingredient has no strength on record ("Glimepiride (NA) + Metformin
    (NA)"). A product like that cannot be checked against any strength a prescription states.
    """
    parts = split_ingredients(composition)
    return bool(parts) and any(not numbers for _, numbers in parts)


_THREE_STRENGTHS_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:mg|mcg)?\s*/\s*\d+(?:\.\d+)?\s*(?:mg|mcg)?\s*/\s*\d+(?:\.\d+)?\s*(?:mg|mcg)", re.IGNORECASE
)


def is_composition_incomplete(name, composition):
    """
    True when the product NAME shows three or more strengths ("100mg/325mg/250mg")
    but the stored composition lists two ingredients or fewer.

    The source CSV has only two composition columns, so a third ingredient is
    lost when the data is imported. Such a product must not be treated as
    equivalent to a genuine two-ingredient product with the same stored composition.
    """
    return bool(_THREE_STRENGTHS_RE.search(name or "")) and len(split_ingredients(composition)) <= 2


def composition_key(composition):
    """
    A whitespace- and case-insensitive identity for a composition, so that
    "Amoxycillin  (500mg) + Clavulanic Acid (125 mg)" equals
    "Amoxycillin (500mg) + Clavulanic Acid (125mg)" but not "... (500mg)".
    """
    return re.sub(r"\s+", "", (composition or "").lower())
