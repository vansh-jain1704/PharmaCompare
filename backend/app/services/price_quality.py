"""
Price-quality rules for comparing a prescribed product with its alternatives.

Nothing here removes or edits a price. A price is FLAGGED, and a flagged (or
otherwise not comparable) alternative is not counted as a saving. Everything is
derived when a comparison is built or read, so no stored data changes.

Why these rules exist (measured on the 253,973-row dataset, see
database/audit_dataset.py):
  - Pack sizes differ. Dolo 650 is a strip of 15 while many alternatives are strips
    of 10, so comparing the pack prices overstates a saving. A saving is counted only
    against an alternative with the SAME pack quantity.
  - A few prices are an order of magnitude away from every comparable product
    (an amoxicillin + clavulanate listed at Rs 6.98 against a Rs 160 median). That may
    be real or a data error; the dataset cannot say. Such a price must not be the
    thing that makes an alternative look attractive.

The extreme-price rule
  A product is "unusually_low" / "unusually_high" when its price PER UNIT is less than
  1/EXTREME_RATIO or more than EXTREME_RATIO times the median unit price of the
  comparable group (same ingredients and strengths, dosage form and release type; live
  products with a price above zero and a readable pack quantity). It is only applied
  to groups of at least MIN_GROUP_SIZE such products, because a median of three prices
  proves nothing. A 10x gap is deliberately wide: Indian generics are legitimately
  several times cheaper than brands, and a tighter rule would flag them.
"""
import re
import statistics

PACK_QTY_RE = re.compile(r"of\s+(\d+(?:\.\d+)?)\s*([A-Za-z]+)?", re.IGNORECASE)
# What the word after the number measures. Anything else ("tablets", "capsule", "Injection")
# is a count of units. Volumes and weights are never mixed with counts or with each other.
_UNIT_KINDS = {"ml": ("ml", 1), "ltr": ("ml", 1000), "litre": ("ml", 1000), "liter": ("ml", 1000), "l": ("ml", 1000),
               "gm": ("g", 1), "g": ("g", 1), "gms": ("g", 1), "kg": ("g", 1000),
               "mg": ("mg", 1), "mcg": ("mcg", 1), "iu": ("iu", 1)}

MIN_GROUP_SIZE = 8
EXTREME_RATIO = 10.0

FLAG_LOW = "unusually_low"
FLAG_HIGH = "unusually_high"
FLAG_NOTES = {
    FLAG_LOW: "This price is far below the usual price per unit for this medicine in the dataset - please verify it before relying on it.",
    FLAG_HIGH: "This price is far above the usual price per unit for this medicine in the dataset - please verify it before relying on it.",
}


def parse_pack(pack_size):
    """
    (quantity, kind) of a pack, or None when unreadable. "strip of 15 tablets" -> (15, "count"),
    "bottle of 100 ml Syrup" -> (100, "ml"), "bottle of 1 Ltr Solution" -> (1000, "ml").
    """
    match = PACK_QTY_RE.search(pack_size or "")
    if not match:
        return None
    quantity = float(match.group(1))
    kind, factor = _UNIT_KINDS.get((match.group(2) or "").lower(), ("count", 1))
    quantity *= factor
    return (quantity, kind) if quantity > 0 else None


def pack_quantity(pack_size):
    """Number of units in a pack ("strip of 15 tablets" -> 15.0), or None when unreadable."""
    parsed = parse_pack(pack_size)
    return parsed[0] if parsed else None


def unit_price(price, pack_size):
    parsed = parse_pack(pack_size)
    if price is None or parsed is None or float(price) <= 0:
        return None
    return float(price) / parsed[0]


def same_pack_quantity(pack_a, pack_b):
    """Same amount of the same kind of thing: 10 tablets and 10 ml are not the same quantity."""
    a, b = parse_pack(pack_a), parse_pack(pack_b)
    return a is not None and b is not None and a == b


def group_stats(group_rows):
    """
    Median unit price of a comparable group, from (price, pack_size) pairs, or None
    when the group is too small to say what is "usual".
    """
    by_kind = {}
    for price, pack in group_rows:
        parsed, unit = parse_pack(pack), unit_price(price, pack)
        if parsed is not None and unit is not None:
            by_kind.setdefault(parsed[1], []).append(unit)
    if not by_kind:
        return None
    kind = max(by_kind, key=lambda k: len(by_kind[k]))  # the unit most of the group is sold in
    units = by_kind[kind]
    if len(units) < MIN_GROUP_SIZE:
        return None
    return {"median_unit": statistics.median(units), "n": len(units), "kind": kind}


def classify(price, pack_size, stats):
    """FLAG_LOW / FLAG_HIGH when this price's unit price is extreme for its group, else None."""
    unit = unit_price(price, pack_size)
    parsed = parse_pack(pack_size)
    if unit is None or not stats or parsed[1] != stats["kind"]:
        return None  # nothing to compare it with: judged only against products measured the same way
    median = stats["median_unit"]
    if unit < median / EXTREME_RATIO:
        return FLAG_LOW
    if unit > median * EXTREME_RATIO:
        return FLAG_HIGH
    return None


def counts_for_savings(prescribed_price, prescribed_flag, prescribed_pack,
                       alt_price, alt_flag, alt_pack, alt_discontinued):
    """
    Whether an alternative may be presented as a saving over the prescribed product:
    both prices are real and unflagged, the alternative is live, cheaper, and sold in
    the same pack quantity (so the two prices describe the same amount of medicine).
    """
    if prescribed_price is None or float(prescribed_price) <= 0 or prescribed_flag:
        return False
    if alt_price is None or float(alt_price) <= 0 or alt_flag or alt_discontinued:
        return False
    if not same_pack_quantity(prescribed_pack, alt_pack):
        return False
    return float(alt_price) < float(prescribed_price)
