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


_INGREDIENT_PART_RE = re.compile(r"^\s*(.*?)\s*\((.*)\)\s*$")


def display_strength(composition, fallback=None):
    """
    The strength to show for a product, from its ingredient list: "500mg" for one ingredient, and
    "Domperidone 30mg + Pantoprazole 40mg" for a combination. The Medicines.strength column holds only the FIRST
    ingredient's strength, so a combination shown from it alone ("30mg") understates what the product contains.
    Returns `fallback` (the stored strength) when the composition cannot be read, and None when there is nothing to show.
    """
    parts = [p.strip() for p in re.split(r"\s*\+\s*", composition or "") if p.strip()]
    shown = []
    for part in parts:
        match = _INGREDIENT_PART_RE.match(part)
        if not match or not match.group(2).strip() or match.group(2).strip().upper() == "NA":
            return fallback
        shown.append((match.group(1).strip(), re.sub(r"\s+", "", match.group(2))))
    if not shown:
        return fallback
    if len(shown) == 1:
        return shown[0][1]
    return " + ".join(f"{name} {strength}" for name, strength in shown)
