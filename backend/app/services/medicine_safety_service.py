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
import re

from app.models.safety_model import lookup_interaction_data
from app.services.allergy_service import check_medicine_against_allergies
from app.services.clinical_decision_service import SEVERITY_RANK, _normalize_salt
from app.services import data_validation_service, instruction_service, manual_entry_service, recommendation_notes
from app.services.composition import display_strength, ingredient_numerators
from app.services.display_rounding import percent
from app.services.medicine_matching_service import assess_confirmation, form_conflict_text, is_generic_line, name_matches_exactly
from app.services.match_status import USER_UNMATCHED, is_confirmed
from app.services.release_type import RELEASE_LABELS, detect_line_release, is_modified

INTERACTION_LABELS = {
    "interaction_found": "Interaction on record – see the safety notes and ask your pharmacist.",
    "interactions_checked_none_found": "Checked against the other medicines – no interaction on record. This is not a guarantee.",
    "interaction_data_not_available": "Interaction data not available – please confirm with a pharmacist.",
    "no_known_interactions": "Nothing to compare – this is the only medicine on the prescription.",
}
NOT_IDENTIFIED_INTERACTION_LABEL = "Not checked – this line hasn't been identified yet."

FLAG_REVIEW_SEVERITIES = ("Major", "Moderate")

# What a line's stored match_options object says it holds (see _decode_guesses).
CLOSEST_GUESSES_KIND = "closest_guesses"
NO_CANDIDATE_REASON = ("No product on file resembles this text. It may have been misread, or the brand may not be in the "
                       "dataset.")
UNMATCHED_LABEL = ("You marked this line as not identified. It is not included in the safety, price or savings checks.")
ENTERED_LABEL = ("Entered by you. This medicine is not matched to the dataset, so no price, saving, alternative or medicine-specific "
                 "safety check is shown for it.")
SUGGESTED_PREFIX = "Suggested: "


def allergy_check_status(allergies):
    """
    What the allergy check had to work with, stated plainly. With no allergies saved nothing was compared, and that must never read like
    "no allergy found". Shown on the analysis page and in the PDF.
    """
    saved = [a for a in (allergies or []) if a]
    if not saved:
        return {
            "declared": False, "count": 0,
            "message": "No allergies are saved on your account, so the allergy check did not run. This does NOT mean no allergy was found: "
                       "add your allergies in your profile, then open this report again.",
        }
    return {
        "declared": True, "count": len(saved),
        "message": f"The allergy check compared the medicines you confirmed with the {len(saved)} allergy"
                   f"{'' if len(saved) == 1 else ' entries'} saved on your account. It cannot check a medicine that is not confirmed.",
    }


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


def _decode_guesses(raw):
    """
    The look-alike products the matcher stored for a line it could not settle (see
    medicine_matching_service._closest_guesses). They live in the same JSON column as the several-close-matches
    list, as an object, so the two can never be mistaken for each other.
    """
    if not raw:
        return []
    try:
        decoded = raw if isinstance(raw, (list, dict)) else json.loads(raw)
    except (TypeError, ValueError):
        return []
    if isinstance(decoded, dict) and decoded.get("kind") == CLOSEST_GUESSES_KIND and isinstance(decoded.get("candidates"), list):
        return decoded["candidates"]
    return []


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
    # What the prescription says about dosing for each line, including instruction rows OCR split off below it. Derived here,
    # from the stored OCR lines, so it works for prescriptions analysed before this was read and changes no stored row.
    attached = instruction_service.attach([(r.get("raw_text") or "").strip() for r in pm_rows], ocr_lines or [], lambda t: True)

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
        user_unmatched = row["match_status"] == USER_UNMATCHED
        # the closest look-alikes stored when the matcher could not settle the line (never confirmed)
        guesses = _decode_guesses(row.get("match_options")) if row["match_status"] in ("needs_verification", USER_UNMATCHED) else []
        # a medicine the person typed in for a line the dataset cannot identify (never matched to a product)
        typed = manual_entry_service.decode(row.get("match_options")) if user_unmatched else None
        # A SUGGESTION is a closest guess whose name is the very name written on the line (strength, form or the way the text was read
        # still need a person). It is only ever shown for checking: nothing is priced, compared or safety-checked on it.
        suggestion = None
        if not is_identified and not user_unmatched and not needs_disambiguation and guesses:
            top = guesses[0]
            if top.get("medicine_name") and name_matches_exactly(row.get("raw_text") or "", top["medicine_name"]):
                suggestion = {"medicine_id": top.get("medicine_id"), "medicine_name": top["medicine_name"], "score": top.get("score")}

        # A line that only names ingredients ("Paracetamol 650") is satisfied by any
        # brand, so the product attached to it is a representative, not what was
        # written. A line the person confirmed by hand names a product on purpose.
        brand_unspecified = bool(is_identified and not user_confirmed and is_generic_line(row.get("raw_text"), row))

        # The OCR was unsure of (part of) the very text this match rests on. The person
        # may have confirmed it by hand, which settles it.
        ocr_line = ocr_by_text.get((row.get("raw_text") or "").strip())
        ocr_uncertain = bool(is_identified and not user_confirmed and ocr_line and ocr_line.get("uncertain"))

        # ---- why an unsettled line is unsettled ----------------------------
        # In plain language, from what was stored: nothing here is a new judgement.
        reasons = []
        if not is_identified:
            if needs_disambiguation:
                reasons.append(f"{reason[0].upper()}{reason[1:]}.")
            elif guesses:
                reasons.extend(guesses[0].get("reasons") or [])
            else:
                reasons.append(NO_CANDIDATE_REASON)
            if ocr_line and ocr_line.get("uncertain"):
                pct = ocr_line.get("confidence")
                shown = f" ({percent(pct)}%)" if pct is not None else ""
                reasons.append(f"The text of this line was read with low confidence{shown}, so it may not say what is written on the prescription.")

        # A product the person confirmed although it conflicts with what the line says (name, form, strength, ingredient or
        # release type). Their decision stands, but the figures that rest on it are never counted as a saving: they may
        # describe a different medicine from the one prescribed. Derived on every response, like everything else here.
        confirmation_conflicts = []
        if is_identified and user_confirmed:
            confirmation_conflicts = [f["text"] for f in assess_confirmation(row.get("raw_text"), row) if f["severity"] == "conflict"]

        text_key_for_assumption = (row.get("raw_text") or "").strip()

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
        # The line says one dosage form and the product the matcher picked is another ("Cap ..." matched to a tablet).
        # The match still stands as it was decided, but it is not presented as settled until the person looks at it.
        form_conflict = form_conflict_text(row.get("raw_text"), row.get("form")) if is_identified and not user_confirmed else None
        if form_conflict:
            flags.append(form_conflict)
        # Handwritten "1-0-0" read as "100": the matcher ignored those digits to find the product (see match_line). Say so.
        read_assumption = None
        if is_identified and not user_confirmed:
            own = instruction_service.parse(text_key_for_assumption)
            if own["schedule_certainty"] == "digits_run_together":
                run = own["schedule"].replace("-", "")
                if run not in instruction_service.owned_numbers(row):
                    read_assumption = (f"the number {run} on the line was read as a dose schedule ({own['schedule']}), not a strength, "
                                       "because this product has no such strength")
                    flags.append(read_assumption)
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
            verification_label = "Confirmed by you" + (", although it differs from the prescription line" if confirmation_conflicts else "")
        elif is_identified:
            verification_status = "pending_verification"
            verification_label = "Matched automatically – please check it against your prescription."
        elif user_unmatched and typed:
            verification_status = "entered_by_user"
            verification_label = ENTERED_LABEL
        elif user_unmatched:
            verification_status = "marked_unidentified"
            verification_label = UNMATCHED_LABEL
        else:
            verification_status = "pending_verification"
            if suggestion:
                verification_label = (f"{SUGGESTED_PREFIX}{suggestion['medicine_name']}. The name matches what was read, but the strength, "
                                      "form or the way the text was read still need your check.")
            elif reason:
                verification_label = f"Not identified yet – {reason}."
            elif guesses:
                verification_label = "Not identified yet – only look-alike products were found. Please check them against your prescription."
            else:
                verification_label = "Not identified yet – needs your input."

        # ---- dosing instructions -------------------------------------------------
        text_key = (row.get("raw_text") or "").strip()
        parsed = attached.get(text_key, {}).get("instructions") or instruction_service.parse(text_key)
        if is_identified:
            parsed = instruction_service.drop_schedule_that_is_a_strength(parsed, instruction_service.owned_numbers(row))
        instruction_sources = attached.get(text_key, {}).get("sources") or ([text_key] if text_key else [])
        if typed:
            # the person typed the schedule and duration themselves: read THEIR words, not the OCR line
            duration_words = re.sub(r"^(?:x|×|for)\s*", "", (row.get("duration") or "").strip(), flags=re.IGNORECASE)
            typed_text = " ".join(p for p in [(row.get("frequency") or "").strip(), f"for {duration_words}" if duration_words else ""] if p)
            parsed = instruction_service.parse(typed_text)
            instruction_sources = [typed_text] if typed_text else []

        result[pm_id] = {
            "instructions": {**{k: v for k, v in parsed.items() if k != "slots"}, "slots": parsed["slots"],
                             "text": instruction_service.describe_schedule(parsed), "sources": instruction_sources},
            "interaction_status": interaction_status,
            "interaction_label": interaction_label,
            "interaction_severity": severity,
            "verification_status": verification_status,
            "verification_label": verification_label,
            "flag_reasons": flags,
            "verification_reason": reason,
            # every plain-language reason this line is unsettled, and the look-alikes it was shown
            "verification_reasons": reasons,
            "closest_guesses": guesses,
            "suggested": bool(suggestion),
            "suggestion": suggestion,
            "user_entered": ({**typed, "schedule": row.get("frequency"), "duration": row.get("duration")} if typed else None),
            "user_unmatched": user_unmatched,
            "ocr_uncertain": ocr_uncertain,
            "display_strength": display_strength(row.get("composition"), row.get("strength")) if is_identified else None,
            "alternatives_notes": recommendation_notes.notes_for(
                needs_check=bool(form_conflict or read_assumption), ocr_uncertain=ocr_uncertain, needs_disambiguation=needs_disambiguation,
                confirmed_with_conflicts=bool(confirmation_conflicts),
            ) if is_identified else None,
            "form_conflict": bool(form_conflict),
            "read_assumption": read_assumption,
            "needs_check": bool(form_conflict or read_assumption),
            "confirmed_with_conflicts": bool(confirmation_conflicts),
            "confirmation_conflicts": confirmation_conflicts,
            "ocr_confidence": ocr_line.get("confidence") if ocr_line else None,
            "brand_unspecified": brand_unspecified,
            # missing or inconsistent data on the product itself (only for an identified line: an unconfirmed one names no product)
            "data_notes": data_validation_service.validate_medicine(row) if is_identified else [],
            "release_type": release if is_identified else None,
            "release_label": RELEASE_LABELS.get(release, "modified release") if is_identified and is_modified(release) else None,
            "allergy_alert": bool(allergy),
            "allergy_alert_text": allergy["text"] if allergy else None,
            "needs_disambiguation": needs_disambiguation,
            "match_options": options if needs_disambiguation else [],
        }
    return result
