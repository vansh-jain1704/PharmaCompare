"""
Price Comparison - a self-contained service that runs after the Clinical
Decision Engine. Designed to be imported independently by future modules
(Generic/Alternative Recommendation, Affordability, Availability, the
Smart Health Report) without any coupling to the prescription upload route.

Ground rules enforced here (not just documented - see the code):
  - Only ever compares medicines Medicine Detection actually confirmed.
    A 'needs_verification' line gets a NEEDS_VERIFICATION result, never a
    price comparison.
  - Price data comes from ONE place: Medicines.price, imported from a
    community dataset snapshot (see database/PROVENANCE.md). Never called
    "real-time" - every result carries the actual import date as its
    price_date, and a not-a-live-price disclaimer.
  - "Comparable" means same primary_salt + secondary_salt + strength +
    dosage form + release type (conventional vs sustained/extended/...) + the
    same full composition (every ingredient's strength). Different pack sizes are still shown, but price-per-unit
    is computed so the comparison stays fair, and a flag marks when pack
    sizes differ.
  - Discontinued medicines are always labelled. A discontinued prescribed
    medicine is flagged; discontinued products are excluded from the
    alternatives list (not offered as something to switch to).
  - Never picks or names a "best" alternative - only lists comparable
    products with their price/difference/savings figures. Any actual
    recommendation is out of scope for this module by design.
"""
import re

from app.models.medicine_model import get_prescription_medicines
from app.models.price_model import find_alternatives, get_group_prices, get_price_comparison, save_price_row
from app.services import price_provenance_service, price_quality
from app.services.match_status import is_confirmed

PRICE_SOURCE = "community_dataset:indian-medicine-dataset-github (see database/PROVENANCE.md)"
PACK_QTY_RE = re.compile(r"of\s+(\d+(?:\.\d+)?)", re.IGNORECASE)

NOT_LIVE_PRICE_NOTE = (
    "This price is from an imported reference dataset, not a live market feed - "
    "it may not reflect the current price at any specific pharmacy."
)


def _extract_pack_quantity(pack_size):
    if not pack_size:
        return None
    match = PACK_QTY_RE.search(pack_size)
    return float(match.group(1)) if match else None


def _price_per_unit(price, pack_size):
    qty = _extract_pack_quantity(pack_size)
    if not qty or qty <= 0 or price is None:
        return None
    return round(float(price) / qty, 4)


def _build_alternative_entry(alt_row, prescribed_price, prescribed_pack_size, prescribed_flag=None, stats=None):
    alt_price = float(alt_row["price"])
    alt_per_unit = _price_per_unit(alt_price, alt_row["pack_size"])

    price_difference = round(alt_price - float(prescribed_price), 2)
    same_quantity = price_quality.same_pack_quantity(prescribed_pack_size, alt_row["pack_size"])
    flag = price_quality.classify(alt_price, alt_row["pack_size"], stats)
    # A percentage over a pack of a different size describes two different amounts of
    # medicine, and one built on a price flagged as extreme is not a figure to headline,
    # so it is only given when the quantities match and the price is not flagged.
    savings_percent = (
        round((float(prescribed_price) - alt_price) / float(prescribed_price) * 100, 2)
        if prescribed_price and float(prescribed_price) > 0 and same_quantity and not flag
        else None
    )

    return {
        "medicine_id": alt_row["medicine_id"],
        "medicine_name": alt_row["medicine_name"],
        "manufacturer": alt_row["manufacturer"],
        "strength": alt_row["strength"],
        "form": alt_row["form"],
        "pack_size": alt_row["pack_size"],
        "same_pack_size": (alt_row["pack_size"] or "").strip().lower() == (prescribed_pack_size or "").strip().lower(),
        "price": alt_price,
        "price_per_unit": alt_per_unit,
        "price_difference": price_difference,
        "savings_percent": savings_percent,
        "same_pack_quantity": same_quantity,
        "price_flag": flag,
        "price_flag_note": price_quality.FLAG_NOTES.get(flag),
        "counts_for_savings": price_quality.counts_for_savings(
            prescribed_price, prescribed_flag, prescribed_pack_size,
            alt_price, flag, alt_row["pack_size"], alt_row["is_discontinued"],
        ),
        "is_discontinued": bool(alt_row["is_discontinued"]),
        "data_source": PRICE_SOURCE,
        "price_date": alt_row["imported_at"].isoformat() if alt_row["imported_at"] else None,
    }


def compare_prescription_medicine(pm_row):
    """
    Builds the full structured comparison for one confirmed
    Prescription_Medicines row. Returns None if the medicine wasn't
    confirmed - callers must not attempt a price comparison on an
    unconfirmed guess.
    """
    if not is_confirmed(pm_row["match_status"]) or not pm_row["medicine_id"]:
        return {
            "pm_id": pm_row["pm_id"],
            "raw_text": pm_row["raw_text"],
            "verification_status": "needs_verification",
            "prescribed_medicine": None,
            "reference_price": None,
            "alternatives": [],
            "note": "This medicine was not confidently identified, so no price comparison could be performed.",
        }

    price = pm_row["price"]
    price_reliable = price is not None and float(price) > 0
    pack_size = pm_row.get("pack_size")
    per_unit = _price_per_unit(price, pack_size) if price is not None else None

    # If the dataset lost one of this product's ingredients, "same composition"
    # cannot be established, so no alternatives are offered rather than guessed.
    composition_unreliable = bool(pm_row.get("composition_incomplete"))
    alt_rows = [] if composition_unreliable else find_alternatives(
        pm_row["primary_salt"], pm_row["secondary_salt"], pm_row["strength"], pm_row["form"],
        exclude_medicine_id=pm_row["medicine_id"],
        release_type=pm_row.get("release_type"),
        composition=pm_row.get("composition"),
        pack_quantity=price_quality.pack_quantity(pack_size),
        pack_size=pack_size,
    )
    stats = None
    if alt_rows or price_reliable:
        stats = price_quality.group_stats(get_group_prices(
            pm_row["primary_salt"], pm_row["secondary_salt"], pm_row["strength"], pm_row["form"],
            release_type=pm_row.get("release_type"), composition=pm_row.get("composition"),
        ))
    reference_flag = price_quality.classify(price, pack_size, stats) if price_reliable else None
    alternatives = (
        [_build_alternative_entry(a, price, pack_size, reference_flag, stats) for a in alt_rows] if price is not None else []
    )

    return {
        "pm_id": pm_row["pm_id"],
        "raw_text": pm_row["raw_text"],
        "verification_status": "confirmed",
        "prescribed_medicine": {
            "medicine_id": pm_row["medicine_id"],
            "medicine_name": pm_row["medicine_name"],
            "manufacturer": pm_row["manufacturer"],
            "composition": pm_row["composition"],
            "primary_salt": pm_row["primary_salt"],
            "secondary_salt": pm_row["secondary_salt"],
            "strength": pm_row["strength"],
            "form": pm_row["form"],
            "pack_size": pack_size,
            "is_discontinued": bool(pm_row["is_discontinued"]),
        },
        "reference_price": {
            "price": float(price) if price is not None else None,
            "price_per_unit": per_unit,
            "price_reliable": price_reliable,
            "price_flag": reference_flag,
            "price_flag_note": price_quality.FLAG_NOTES.get(reference_flag),
            "data_source": PRICE_SOURCE,
            "price_date": None,  # filled in by caller from Medicines.imported_at
            "note": NOT_LIVE_PRICE_NOTE,
        },
        "alternatives": alternatives,
        "alternatives_found": len(alternatives) > 0,
        "note": (
            "The reference price on file for this medicine is missing or zero and should not be relied on."
            if not price_reliable else
            "The ingredient list in the dataset is incomplete for this product, so no alternatives are offered."
            if composition_unreliable else
            price_quality.FLAG_NOTES.get(reference_flag)
        ),
    }


def annotate_price_rows(rows):
    """
    The stored Price_Comparison rows, with the same price-quality fields a fresh
    comparison carries (price_flag, same_pack_quantity, counts_for_savings).

    Derived on every read rather than stored, like the safety summary: it works for
    prescriptions analysed before these rules existed and can never disagree with
    them. savings_percent is withheld when the pack quantities differ.
    """
    by_pm = {}
    for row in rows:
        by_pm.setdefault(row["pm_id"], []).append(row)

    # Where each price came from and how old the snapshot is, derived on every read from the stored import date (never stored).
    for row in rows:
        row["price_basis"] = price_provenance_service.reference_basis(row.get("price_date"))

    stats_cache = {}
    for group in by_pm.values():
        prescribed = next((r for r in group if r["row_type"] == "prescribed"), None)
        if prescribed is None:
            continue
        key = (prescribed["primary_salt"], prescribed["secondary_salt"], prescribed["strength"], prescribed["form"],
               prescribed["release_type"], prescribed["composition"])
        if key not in stats_cache:
            stats_cache[key] = price_quality.group_stats(get_group_prices(*key[:5], composition=key[5]))
        stats = stats_cache[key]

        reference_flag = price_quality.classify(float(prescribed["price"]), prescribed["pack_size"], stats)
        prescribed["price_flag"] = reference_flag
        prescribed["price_flag_note"] = price_quality.FLAG_NOTES.get(reference_flag)
        prescribed["counts_for_savings"] = False
        for alt in group:
            if alt is prescribed:
                continue
            flag = price_quality.classify(float(alt["price"]), alt["pack_size"], stats)
            same_quantity = price_quality.same_pack_quantity(prescribed["pack_size"], alt["pack_size"])
            alt["price_flag"] = flag
            alt["price_flag_note"] = price_quality.FLAG_NOTES.get(flag)
            alt["same_pack_quantity"] = same_quantity
            alt["counts_for_savings"] = price_quality.counts_for_savings(
                prescribed["price"], reference_flag, prescribed["pack_size"],
                alt["price"], flag, alt["pack_size"], alt["is_discontinued"],
            )
            if not same_quantity or flag:
                alt["savings_percent"] = None
    return rows


def get_annotated_price_comparison(prescription_id):
    return annotate_price_rows(get_price_comparison(prescription_id))


def run_price_comparison(prescription_id):
    """
    Orchestrates price comparison for every line in a prescription,
    persists a Price_Comparison row for the prescribed medicine and each
    alternative found, and returns the full structured result list.
    Safe to call on a prescription with zero confirmed medicines.
    """
    prescription_medicines = get_prescription_medicines(prescription_id)
    results = []

    for pm in prescription_medicines:
        comparison = compare_prescription_medicine(pm)

        if comparison["verification_status"] == "confirmed" and comparison["reference_price"]["price"] is not None:
            price_date = pm["imported_at"].isoformat() if pm.get("imported_at") else None
            comparison["reference_price"]["price_date"] = price_date
            comparison["reference_price"]["price_basis"] = price_provenance_service.reference_basis(price_date)
            for alt in comparison["alternatives"]:
                alt["price_basis"] = price_provenance_service.reference_basis(alt["price_date"])

            save_price_row(
                pm["pm_id"], pm["medicine_id"], "prescribed",
                comparison["reference_price"]["price"],
                comparison["reference_price"]["price_per_unit"],
                pm.get("pack_size"),
                None, None,
                bool(pm["is_discontinued"]),
                PRICE_SOURCE,
                pm["imported_at"],
            )
            for alt in comparison["alternatives"]:
                save_price_row(
                    pm["pm_id"], alt["medicine_id"], "alternative",
                    alt["price"], alt["price_per_unit"], alt["pack_size"],
                    alt["price_difference"], alt["savings_percent"],
                    alt["is_discontinued"], PRICE_SOURCE,
                    alt["price_date"],
                )

        results.append(comparison)

    return results
