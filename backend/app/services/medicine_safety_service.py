"""
Per-medicine safety summary: the two separate questions the UI used to blur
into one "Needs Verification" badge.

  interaction_status   - what the interaction database could tell us
  verification_status  - who has confirmed that this line IS this medicine

They answer different things. A medicine can be confidently identified (so
verification is fine) while DDInter simply has no data on it (so the
interaction answer is "unknown"). Collapsing them made a correctly identified
medicine look unresolved, which is the contradiction this module removes.

Nothing here is stored. It is derived on every response from the same
records the clinical engine uses, so it can never disagree with them or go
stale when a user corrects a medicine or edits their allergies.

interaction_status values
  interaction_found                  a DDInter record involves this medicine
  interactions_checked_none_found    every other medicine was checkable and
                                     DDInter holds no record for the pair
  interaction_data_not_available     at least one comparison could not be made
                                     because DDInter does not track a substance
  no_known_interactions              nothing to compare against (the only
                                     medicine on the prescription)
  ("interaction_found" is not in the original spec's list of three; without a
  value for "there IS an interaction" the field could not carry the one result
  that matters most.)

None of these says "safe". The labels avoid that word on purpose.
"""
import json

from app.models.safety_model import lookup_interaction_data
from app.services.allergy_service import check_medicine_against_allergies
from app.services.clinical_decision_service import SEVERITY_RANK, _normalize_salt
from app.services.composition import ingredient_numerators
from app.services.medicine_matching_service import is_generic_line
from app.services.match_status import is_confirmed
from app.services.release_type import RELEASE_LABELS, detect_line_release, is_modified

INTERACTION_LABELS = {
    "interaction_found": "Interaction on record – see the safety notes and ask your pharmacist.",
    "interactions_checked_none_found": "Checked against the other medicines – no interaction on record. This is not a guarantee.",
    "interaction_data_not_available": "Interaction data not available – please confirm with a pharmacist.",
    "no_known_interactions": "Nothing to compare – this is the only medicine on the prescription.",
}
NOT_IDENTIFIED_INTERACTION_LABEL = "Not checked – this line hasn't been identified yet."

FLAG_REVIEW_SEVERITIES = ("Major", "Moderate")


def _variants(salt):
    if not salt or not salt.strip():
        return []
    plain = salt.strip().lower()
    normalised = _normalize_salt(salt)
    return [plain] if normalised == plain else [plain, normalised]


def _pair_record(pairs, variants_a, variants_b):
    for a in variants_a:
        for b in variants_b:
            if frozenset((a, b)) in pairs:
                return pairs[frozenset((a, b))]
    return None


def _decode_options(raw):
    if not raw:
        return []
    if isinstance(raw, (list, dict)):
        return raw if isinstance(raw, list) else []
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return decoded if isinstance(decoded, list) else []


def ambiguity_reason(options):
    """
    Why a line with several candidate products could not be settled, worked out from
    what actually differs between them ("strength", "dosage form", "release type").
    Derived from the stored options, never stored itself.
    """
    if len(options) < 2:
        return None
    axes = []
    if len({tuple(ingredient_numerators(o.get("composition"))) for o in options}) > 1:
        axes.append("strength")
    if len({(o.get("form") or "").strip().lower() for o in options}) > 1:
        axes.append("dosage form")
    if len({o.get("release_type") for o in options}) > 1:
        axes.append("release type")
    what = " or ".join(axes) if axes else "product"
    return f"the prescription does not say which {what} was meant, and several different products fit"


def annotate(pm_rows, allergies, ocr_lines=None):
    """
    pm_rows   - rows from get_prescription_medicines (flat, joined with Medicines)
    allergies - the user's declared allergies (list of strings, may be empty)
    ocr_lines - the stored per-line OCR results ({"text", "confidence", "uncertain"}); a line
                the OCR itself was unsure about is never presented as a settled match

    Returns {pm_id: {...}} with every field the UI needs for the safety and
    verification lines and the allergy alert.
    """
    confirmed = [r for r in pm_rows if is_confirmed(r["match_status"]) and r["medicine_id"]]
    variants_by_pm = {r["pm_id"]: _variants(r.get("primary_salt")) for r in confirmed}

    all_variants = [v for vs in variants_by_pm.values() for v in vs]
    pairs, covered = lookup_interaction_data(all_variants)

    ocr_by_text = {(l.get("text") or "").strip(): l for l in (ocr_lines or [])}

    result = {}
    for row in pm_rows:
        pm_id = row["pm_id"]
        is_identified = is_confirmed(row["match_status"]) and bool(row["medicine_id"])
        user_confirmed = row["match_status"] == "user_confirmed"

        # ---- interaction ---------------------------------------------------
        severity = None
        if not is_identified:
            interaction_status = "interaction_data_not_available"
            interaction_label = NOT_IDENTIFIED_INTERACTION_LABEL
        else:
            mine = variants_by_pm.get(pm_id, [])
            found, checkable, comparable = [], True, 0
            for other in confirmed:
                if other["pm_id"] == pm_id:
                    continue
                theirs = variants_by_pm.get(other["pm_id"], [])
                if mine and theirs and (set(mine) & set(theirs)):
                    continue  # same salt: that is a duplicate-therapy matter, not an interaction
                comparable += 1
                record = _pair_record(pairs, mine, theirs) if mine and theirs else None
                if record:
                    found.append(record)
                elif not (mine and theirs and any(v in covered for v in mine) and any(v in covered for v in theirs)):
                    checkable = False

            if found:
                interaction_status = "interaction_found"
                severity = max(found, key=lambda s: SEVERITY_RANK.get(s, 0))
            elif comparable == 0:
                interaction_status = "no_known_interactions"
            elif checkable:
                interaction_status = "interactions_checked_none_found"
            else:
                interaction_status = "interaction_data_not_available"
            interaction_label = INTERACTION_LABELS[interaction_status]
            if severity and severity != "Unknown":
                interaction_label = f"{severity} interaction on record – see the safety notes and ask your pharmacist."

        # ---- allergy -------------------------------------------------------
        allergy = check_medicine_against_allergies(row, allergies) if is_identified else None

        # ---- disambiguation ------------------------------------------------
        # An unsettled line (needs_verification) can carry candidates too: that is how a
        # generic name with several strengths/forms is handed to the person to choose.
        options = _decode_options(row.get("match_options")) if row["match_status"] in ("matched", "needs_verification") else []
        needs_disambiguation = len(options) >= 2
        reason = ambiguity_reason(options) if needs_disambiguation and not is_identified else None

        # A line that only names ingredients ("Paracetamol 650") is satisfied by any
        # brand, so the product attached to it is a representative, not what was
        # written. A line the person confirmed by hand names a product on purpose.
        brand_unspecified = bool(is_identified and not user_confirmed and is_generic_line(row.get("raw_text"), row))

        # The OCR was unsure of (part of) the very text this match rests on. The person
        # may have confirmed it by hand, which settles it.
        ocr_line = ocr_by_text.get((row.get("raw_text") or "").strip())
        ocr_uncertain = bool(is_identified and not user_confirmed and ocr_line and ocr_line.get("uncertain"))

        # ---- verification --------------------------------------------------
        flags = []
        if needs_disambiguation:
            flags.append("several close matches")
        # A sustained/extended-release product picked for a line that does not say
        # so is not interchangeable with the conventional tablet the prescriber may
        # have meant, so it is never presented as settled. (Derived here, not stored.)
        release = row.get("release_type")
        if is_identified and not user_confirmed and is_modified(release) and detect_line_release(row.get("raw_text")) is None:
            flags.append(f"matched product is {RELEASE_LABELS.get(release, 'modified release')}, which the prescription does not state")
        if ocr_uncertain:
            flags.append("the prescription text was read with low confidence")
        if allergy:
            flags.append("allergy alert")
        if severity in FLAG_REVIEW_SEVERITIES:
            flags.append(f"{severity.lower()} interaction on record")

        if flags and is_identified:
            verification_status = "flagged_for_review"
            verification_label = "Flagged for review: " + "; ".join(flags) + "."
        elif user_confirmed:
            verification_status = "verified_by_user"
            verification_label = "Confirmed by you"
        elif is_identified:
            verification_status = "pending_verification"
            verification_label = "Matched automatically – please check it against your prescription."
        else:
            verification_status = "pending_verification"
            verification_label = (f"Not identified yet – {reason}." if reason else "Not identified yet – needs your input.")

        result[pm_id] = {
            "interaction_status": interaction_status,
            "interaction_label": interaction_label,
            "interaction_severity": severity,
            "verification_status": verification_status,
            "verification_label": verification_label,
            "flag_reasons": flags,
            "verification_reason": reason,
            "ocr_uncertain": ocr_uncertain,
            "ocr_confidence": ocr_line.get("confidence") if ocr_line else None,
            "brand_unspecified": brand_unspecified,
            "release_type": release if is_identified else None,
            "release_label": RELEASE_LABELS.get(release, "modified release") if is_identified and is_modified(release) else None,
            "allergy_alert": bool(allergy),
            "allergy_alert_text": allergy["text"] if allergy else None,
            "needs_disambiguation": needs_disambiguation,
            "match_options": options if needs_disambiguation else [],
        }
    return result
