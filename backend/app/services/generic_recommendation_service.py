"""
Generic/Alternative Recommendation - builds on Price Comparison's already-
computed, already-tested alternatives list to surface up to 3 cheaper,
same-composition options per prescribed medicine, each with the objective
facts behind it. Never picks a single "winner", never tells the user to
switch - every recommendation is presented as information to discuss with
a doctor or pharmacist, consistent with every other module in this
project.

Safety rules enforced here (inherits Price Comparison's rules by
construction - same-salt/strength/form only, discontinued alternatives
already excluded, never invented prices):
  - Only ever generated for a medicine Medicine Detection confirmed AND
    Price Comparison found a reliable, priced reference for.
  - An alternative is only recommendable if it is strictly cheaper than
    the prescribed medicine and its own price is reliable (>0) -
    re-checked here rather than assumed, in case that ever changes
    upstream.
  - confidence_score reflects objective corroboration only (savings
    margin, number of comparable alternatives) - never a guess about
    clinical suitability.
  - reason text states only verifiable facts (salt, strength, form,
    price, source) plus the standard doctor/pharmacist verification line.
"""
from app.models.recommendation_model import save_recommendation

DATA_SOURCE = "PharmaCompare local analysis (derived from Price Comparison)"
DOCTOR_ADVICE = "This is not a recommendation to switch medicines - please confirm with your doctor or pharmacist first."
MAX_RECOMMENDATIONS_PER_MEDICINE = 3
MEANINGFUL_SAVINGS_PERCENT = 20.0
MIN_ALTERNATIVES_FOR_HIGH_CONFIDENCE = 2


def _confidence_for(alt, num_alternatives):
    """
    1.0: a meaningful price gap (>=20%) AND more than one comparable
         alternative exists (some corroboration, not a single data point)
    0.7: cheaper, but only a small margin or just one alternative found
    0.0: not actually cheaper (never persisted - filtered out by the caller)
    """
    savings = alt.get("savings_percent") or 0
    if savings >= MEANINGFUL_SAVINGS_PERCENT and num_alternatives >= MIN_ALTERNATIVES_FOR_HIGH_CONFIDENCE:
        return 1.0
    if savings > 0:
        return 0.7
    return 0.0


def build_recommendations_for_medicine(comparison_entry):
    """
    Takes one entry from price_comparison_service's output (for a single
    confirmed prescribed medicine) and returns up to
    MAX_RECOMMENDATIONS_PER_MEDICINE recommendation dicts - only for
    alternatives that are strictly cheaper and reliably priced. Returns
    an empty list when there's nothing honest to recommend (unconfirmed
    medicine, unreliable reference price, or no cheaper option exists).
    """
    if comparison_entry.get("verification_status") != "confirmed":
        return []
    ref_price = comparison_entry.get("reference_price")
    if not ref_price or not ref_price.get("price_reliable"):
        return []

    prescribed = comparison_entry["prescribed_medicine"]
    alternatives = comparison_entry.get("alternatives") or []

    cheaper = [
        alt for alt in alternatives
        if alt.get("price") is not None and alt["price"] > 0
        and alt.get("price_difference") is not None and alt["price_difference"] < 0
        and not alt.get("is_discontinued")
        # Same pack quantity and no extreme-price flag: a cheaper-looking price that
        # fails these is not a saving worth suggesting (see price_quality).
        and alt.get("counts_for_savings")
    ]
    if not cheaper:
        return []

    num_alternatives = len(cheaper)
    recommendations = []
    for alt in cheaper[:MAX_RECOMMENDATIONS_PER_MEDICINE]:
        confidence = _confidence_for(alt, num_alternatives)
        composition_note = prescribed["primary_salt"]
        if prescribed.get("secondary_salt"):
            composition_note += f" + {prescribed['secondary_salt']}"

        reason = (
            f"Same active ingredient ({composition_note}), same strength ({prescribed['strength']}) "
            f"and dosage form ({prescribed['form']}). Priced at ₹{alt['price']:.2f} vs "
            f"₹{ref_price['price']:.2f} for the prescribed product "
            f"({abs(alt['savings_percent']):.0f}% less). {DOCTOR_ADVICE}"
        )
        recommendations.append({
            "pm_id": comparison_entry["pm_id"],
            "recommended_medicine_id": alt["medicine_id"],
            "generic_name": alt["medicine_name"],
            "price_difference": alt["price_difference"],
            "confidence_score": confidence,
            "reason": reason,
            "data_source": DATA_SOURCE,
        })
    return recommendations


def run_generic_recommendations(price_comparison_results):
    """
    Takes the full output of price_comparison_service.run_price_comparison
    (a list of per-medicine comparison entries) and generates + persists
    recommendations for each confirmed medicine. Returns the full list of
    generated recommendations. Safe to call with an empty list.
    """
    all_recommendations = []
    for entry in price_comparison_results:
        recs = build_recommendations_for_medicine(entry)
        for rec in recs:
            save_recommendation(
                rec["pm_id"], rec["recommended_medicine_id"], rec["generic_name"],
                rec["price_difference"], rec["confidence_score"], rec["reason"], rec["data_source"],
            )
        all_recommendations.extend(recs)
    return all_recommendations
