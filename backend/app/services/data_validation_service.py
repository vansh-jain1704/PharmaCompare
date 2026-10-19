"""
Checking the medicine reference data against ITSELF: names, strengths, dosage forms, ingredients and prices.

The medicine dataset is a community project and does not say where its data came from, so it is never trusted blindly. Each product is checked for
what can be checked WITHOUT any outside source - whether its own fields agree with each other:

  strength_not_in_composition   the name states a strength with a unit ("... 500mg ...") that matches no ingredient strength or their total, after unit
                                conversion. Often the same amount written another way (3% = 30mg/ml), so it says "could not be matched", not "wrong"
  form_disagrees_with_name      the name says Syrup / Injection / Capsule ... but the form on record is something else
  no_composition                no ingredient information at all
  ingredient_list_incomplete    the name shows more ingredients than the two the source holds (see composition.is_composition_incomplete)
  no_strength / no_form / no_pack_size   the field is empty
  no_usable_price               no price, or a price of zero or less

A note is a reason to look twice, never a correction: nothing here changes a row, and a product with notes is still searchable. What it cannot
do is say whether a value is TRUE: agreement between two fields of one community dataset is not clinical verification. A bare number in a brand
name ("Pan 40") is NOT checked, because brand numbers are not always strengths.

Pure functions over a product row (a dict), so they run on any product on its way to the screen, and a table scan for the quality report.
"""
import re

from app.services.medicine_matching_service import _form_mismatch

# strengths written WITH a unit in the name ("Amoxycillin 500mg", "Vitamin D3 60000 IU"); a bare number is a brand number, not checked
NAME_STRENGTH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|ug|gm|g|iu|%)(?![a-z])", re.IGNORECASE)
MISSING_VALUES = {"", "na", "n/a", "nan", "none", "null", "-"}
# a strength in a base unit per family, so "1.2gm" and "1200mg" are the same amount; IU and % are compared only with themselves
_TO_BASE = {"mg": ("mass", 1.0), "g": ("mass", 1000.0), "gm": ("mass", 1000.0), "mcg": ("mass", 0.001), "ug": ("mass", 0.001),
            "iu": ("iu", 1.0), "%": ("percent", 1.0)}

NOTES = {
    "strength_not_in_composition": ("warn", "The strength in the name could not be matched to the ingredient strengths on record (it may be written another way, such as a % or a per-ml concentration). Check it against the pack."),
    "form_disagrees_with_name": ("warn", "The name points to one dosage form but the form on record is another."),
    "no_composition": ("warn", "No ingredient information is on record for this product."),
    "ingredient_list_incomplete": ("warn", "The ingredient list is incomplete in the dataset (it holds at most two ingredients), so this product is never offered as an equivalent."),
    "no_strength": ("info", "No strength is on record."),
    "no_form": ("info", "No dosage form is on record."),
    "no_pack_size": ("info", "No pack size is on record, so prices cannot be compared per unit."),
    "no_usable_price": ("warn", "No usable price is on record."),
}


def _amounts(text):
    """[(family, value)] for every strength with a unit written in the text, in a base unit."""
    out = []
    for number, unit in NAME_STRENGTH_RE.findall(text or ""):
        family, factor = _TO_BASE[unit.lower()]
        out.append((family, round(float(number) * factor, 6)))
    return out


def _explained(stated, recorded):
    """
    True when the strengths stated in the name are accounted for by the ingredient strengths: any one of them matches an ingredient, or the
    amount is the TOTAL of the mass ingredients ("1.2gm" for 1000mg + 200mg, "625mg" for 500mg + 125mg).
    """
    if not stated or not recorded:
        return True
    mass_total = round(sum(v for f, v in recorded if f == "mass"), 6)     # `recorded` is a list: two 500mg ingredients total 1000mg
    return any((family, value) in recorded or (family == "mass" and value == mass_total) for family, value in stated)


def _missing(value):
    return value is None or str(value).strip().lower() in MISSING_VALUES


def validate_medicine(row):
    """
    The notes for one product, [{"code", "level", "text"}], empty when every check passes. `row` needs medicine_name, composition, form, strength,
    pack_size, price and composition_incomplete (missing keys count as missing values).
    """
    codes = []
    name, composition, form = row.get("medicine_name") or "", row.get("composition"), row.get("form")

    if _missing(composition):
        codes.append("no_composition")
    else:
        if not _explained(_amounts(name), _amounts(composition)):
            codes.append("strength_not_in_composition")
    if row.get("composition_incomplete"):
        codes.append("ingredient_list_incomplete")
    if not _missing(form) and name and _form_mismatch(name, form):
        codes.append("form_disagrees_with_name")
    if _missing(row.get("strength")):
        codes.append("no_strength")
    if _missing(form):
        codes.append("no_form")
    if _missing(row.get("pack_size")):
        codes.append("no_pack_size")
    price = row.get("price")
    if price is None or float(price) <= 0:
        codes.append("no_usable_price")
    return [{"code": c, "level": NOTES[c][0], "text": NOTES[c][1]} for c in codes]


def data_notes(row, warn_only=False):
    """What the screens show beside a product: the notes, optionally only the ones that say fields disagree or data is missing."""
    notes = validate_medicine(row)
    return [n for n in notes if n["level"] == "warn"] if warn_only else notes


def scan_table(cursor, examples=3, limit=None):
    """
    Checks every product and returns {"checked", "with_notes", "by_code": {code: {"count", "examples": [{"medicine_id", "name"}]}}}. Read-only.
    Streams the table in one pass; `limit` is for tests.
    """
    cursor.execute(
        "SELECT medicine_id, medicine_name, composition, form, strength, pack_size, price, composition_incomplete FROM Medicines"
        + (f" LIMIT {int(limit)}" if limit else "")
    )
    by_code = {code: {"count": 0, "examples": []} for code in NOTES}
    checked = with_notes = 0
    columns = ["medicine_id", "medicine_name", "composition", "form", "strength", "pack_size", "price", "composition_incomplete"]
    for record in cursor:
        row = dict(zip(columns, record))
        checked += 1
        notes = validate_medicine(row)
        if notes:
            with_notes += 1
        for note in notes:
            slot = by_code[note["code"]]
            slot["count"] += 1
            if len(slot["examples"]) < examples:
                slot["examples"].append({"medicine_id": row["medicine_id"], "name": row["medicine_name"]})
    return {"checked": checked, "with_notes": with_notes, "by_code": by_code}
