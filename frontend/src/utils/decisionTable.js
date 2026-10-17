// Builds the unified "Medicine Decision Table" rows from the raw backend
// response (works for both the upload response and the full prescription
// detail response - same field names, slightly different nested shapes,
// already reconciled by medicineDisplay.js's normalizers).
//
// Every value shown here is derived from real backend data. Nothing is
// invented: frequency is pattern-matched from the actual OCR text (not
// guessed), availability is either "Discontinued" (real is_discontinued
// flag) or an honest "Confirm with your pharmacy" (we have no live stock
// data), and safety status is derived only from real Clinical Decision
// Engine findings.

import {
  normalizeDetectedMedicine,
  normalizePriceComparison,
  groupRecommendations,
  isConfirmedStatus,
} from "./medicineDisplay";

const FREQUENCY_PATTERNS = [
  { re: /\bfour\s*times|qid\b/i, label: "4 times daily" },
  { re: /\bthrice\s*(a\s*)?day|tds\b|tid\b|three\s*times/i, label: "3 times daily" },
  { re: /\btwice\s*(a\s*)?day|bd\b|bid\b/i, label: "Twice daily" },
  { re: /\bonce\s*(a\s*)?day|\bod\b/i, label: "Once daily" },
  { re: /\bevery\s*(\d+)\s*hours?/i, label: null },
  { re: /\bat\s*night|bedtime|\bhs\b/i, label: "At night" },
  { re: /\bmorning\b/i, label: "Morning" },
  { re: /\bsos\b|as\s*needed|if\s*needed|if\s*required/i, label: "As needed" },
];

export function deriveFrequency(rawText) {
  if (!rawText) return null;
  for (const p of FREQUENCY_PATTERNS) {
    const m = rawText.match(p.re);
    if (m) return p.label || `Every ${m[1]} hours`;
  }
  return null;
}

// Two separate questions, answered separately (the old single badge blurred
// them: a correctly identified medicine with no interaction data read as
// "Needs Verification"). Both statuses and their wording come from the
// backend (medicine_safety_service); this only maps them to a visual tone.
export const INTERACTION_TONE = {
  interaction_found: "risk",
  interactions_checked_none_found: "ok",
  no_known_interactions: "ok",
  interaction_data_not_available: "muted",
};
export const VERIFICATION_TONE = {
  verified_by_user: "ok",
  pending_verification: "warn",
  flagged_for_review: "risk",
};

// Short badge text for the table row; the backend's full sentence stays
// available in the row's detail ("Safety check") and as the badge tooltip.
const INTERACTION_SHORT = {
  interaction_found: "Interaction on record",
  interactions_checked_none_found: "No interaction found",
  no_known_interactions: "Nothing to compare",
  interaction_data_not_available: "Interaction data not available",
};
const VERIFICATION_SHORT = {
  verified_by_user: "Confirmed by you",
  pending_verification: "Please check match",
  flagged_for_review: "Flagged for review",
};

const FALLBACK_INTERACTION_LABEL = "Interaction data not available – please confirm with a pharmacist.";
const FALLBACK_VERIFICATION_LABEL = "Not yet verified – please check it against your prescription.";

function buildSafety(raw, item) {
  const interactionStatus = raw.interaction_status || "interaction_data_not_available";
  const verificationStatus =
    raw.verification_status || (item.status === "user_confirmed" ? "verified_by_user" : "pending_verification");
  const severity = raw.interaction_severity;
  let interactionTone = INTERACTION_TONE[interactionStatus] || "muted";
  if (interactionStatus === "interaction_found" && severity === "Minor") interactionTone = "warn";
  const identified = isConfirmedStatus(item.status) && !!item.medicine;
  const interactionShort = !identified
    ? "Not checked yet"
    : interactionStatus === "interaction_found" && severity && severity !== "Unknown"
      ? `${severity} interaction`
      : INTERACTION_SHORT[interactionStatus] || "Interaction data not available";
  const verificationShort = !identified ? "Not identified yet" : VERIFICATION_SHORT[verificationStatus] || "Please check match";
  return {
    interactionShort,
    verificationShort,
    interactionStatus,
    interactionLabel: raw.interaction_label || FALLBACK_INTERACTION_LABEL,
    interactionTone,
    verificationStatus,
    verificationLabel: raw.verification_label || FALLBACK_VERIFICATION_LABEL,
    verificationTone: VERIFICATION_TONE[verificationStatus] || "warn",
    allergyAlert: !!raw.allergy_alert,
    allergyAlertText: raw.allergy_alert_text || null,
    needsDisambiguation: !!raw.needs_disambiguation,
    matchOptions: Array.isArray(raw.match_options) ? raw.match_options : [],
    // Why several products fit, and whether the line names only ingredients (so the
    // product shown is one example of many). Both derived by the backend.
    verificationReason: raw.verification_reason || null,
    // The OCR itself was unsure of this line, so the match is never shown as settled.
    ocrUncertain: !!raw.ocr_uncertain,
    brandUnspecified: !!raw.brand_unspecified,
    releaseLabel: raw.release_label || null,
  };
}

function buildWhyReason(item, safety) {
  if (!item.medicine && safety?.needsDisambiguation && safety.matchOptions.length > 1) {
    const reason = safety.verificationReason ? `${safety.verificationReason[0].toUpperCase()}${safety.verificationReason.slice(1)}.` : "";
    return `${reason} We have not picked one for you - choose the product that matches your prescription.`.trim();
  }
  if (!item.medicine) {
    return `No medicine in our database matched "${item.raw_text}". This text could not be identified.`;
  }
  const confidencePct = item.confidence != null ? Math.round(item.confidence * 100) : null;
  if (!isConfirmedStatus(item.status)) {
    return (
      `This is our closest guess - "${item.medicine.medicine_name}" - but the match confidence` +
      (confidencePct != null ? ` (${confidencePct}%)` : "") +
      ` was too low to confirm automatically. Please verify this against the original prescription.`
    );
  }
  const lowOcr = safety?.ocrUncertain
    ? " The text of this line was read with low confidence, so please check it against the original prescription."
    : "";
  const strengthMentioned = /\d/.test(item.raw_text || "");
  return (
    `The prescription text "${item.raw_text}" was matched to ${item.medicine.medicine_name}` +
    (item.medicine.composition ? ` (contains ${item.medicine.composition})` : "") +
    `, strength ${item.medicine.strength || "not specified"}, form ${item.medicine.form || "not specified"}. ` +
    `Match confidence: ${confidencePct != null ? confidencePct + "%" : "n/a"}, based on the medicine name/salt` +
    (strengthMentioned ? " and strength" : "") +
    " matching our records." + lowOcr
  );
}

function keyFor(obj) {
  return obj.pm_id != null ? `pm:${obj.pm_id}` : `text:${obj.raw_text}`;
}

/**
 * The upload response and the history response identify the same
 * prescription line differently: history rows come from the DB and carry a
 * pm_id, while the upload response's detected_medicines carry only raw_text.
 * Price comparison rows carry BOTH, so they bridge the two - without this,
 * every price/alternative lookup silently missed on the upload page and
 * every medicine read "Price unavailable / No alternative found".
 */
function buildPmIdResolver(priceItems) {
  const pmIdByRawText = {};
  priceItems.forEach((p) => {
    if (p.pm_id != null && p.raw_text != null) pmIdByRawText[p.raw_text] = p.pm_id;
  });
  return (row) => (row.pm_id != null ? row.pm_id : pmIdByRawText[row.raw_text] ?? null);
}

/**
 * The row's one status word, the same four the PDF report uses: matched / confirmed in
 * green, anything uncertain in orange. (Kept here, not in the component, so a test can
 * compare it with the backend's wording.)
 */
export function rowStatus(row) {
  if (!row.doctorMedicine) return { tone: "warn", text: "Needs verification" };
  if (row.status === "user_confirmed") return { tone: "ok", text: "Confirmed" };
  if (row.needsDisambiguation || row.ocrUncertain) return { tone: "warn", text: "Check match" };
  return { tone: "ok", text: "Matched" };
}

/** Under the status pill: the matcher's real score, or who confirmed the line. */
export function confidenceText(row) {
  if (row.status === "user_confirmed") return "Confirmed by you";
  // No single product was named: there is no confidence to quote.
  if (!row.doctorMedicine && row.needsDisambiguation) return `${row.matchOptions.length} possible products`;
  if (row.confidence == null) return "No match found";
  const pct = Math.round(row.confidence * 100);
  // An unidentified line's score belongs to a guess we did not accept.
  return row.doctorMedicine ? `${pct}% confidence` : `Closest guess: ${pct}%`;
}

/**
 * Adds up what switching to the cheapest comparable alternative would save
 * across the whole prescription.
 *
 * Counts only rows that have BOTH a reliable reference price and a real
 * alternative, so the headline can never be inflated by medicines we
 * couldn't actually price. `pricedCount` vs `totalCount` lets the UI say
 * how much of the prescription the figure actually covers.
 */
export function summarizeSavings(rows) {
  // Same rule as the PDF report: a line with an allergy alert, or one still waiting on a
  // "check match" decision, is never added to the total, so screen and PDF cannot disagree.
  const savable = rows.filter(
    (r) => r.savingAmount != null && r.savingAmount > 0 && !r.allergyAlert && !r.needsDisambiguation && !r.ocrUncertain,
  );
  const totalSaving = savable.reduce((sum, r) => sum + r.savingAmount, 0);
  const originalTotal = savable.reduce((sum, r) => sum + (r.prescribedPrice || 0), 0);
  return {
    totalSaving,
    originalTotal,
    savableCount: savable.length,
    pricedCount: rows.filter((r) => r.priceReliable).length,
    totalCount: rows.length,
    percent: originalTotal > 0 ? (totalSaving / originalTotal) * 100 : null,
  };
}

/**
 * detail: the raw API response object - either the upload response or the
 * full GET /api/prescriptions/<id> response. Both use the same field
 * names (detected_medicines, clinical_analysis, price_comparison,
 * recommendations).
 */
export function buildDecisionRows(detail) {
  const detectedRaw = detail.detected_medicines || [];
  const findings = detail.clinical_analysis?.findings || [];
  const priceItems = normalizePriceComparison(detail.price_comparison);
  const recGroups = groupRecommendations(detail.recommendations, priceItems);

  const resolvePmId = buildPmIdResolver(priceItems);

  const priceByKey = {};
  priceItems.forEach((p) => {
    priceByKey[keyFor(p)] = p;
  });
  const recByKey = {};
  recGroups.forEach((g) => {
    recByKey[keyFor(g)] = g.recommendations;
  });

  return detectedRaw.map((raw, index) => {
    const item = normalizeDetectedMedicine(raw);
    const pmId = resolvePmId(raw);
    const key = pmId != null ? `pm:${pmId}` : `text:${raw.raw_text}`;
    const priceEntry = priceByKey[key];
    const recommendations = recByKey[key] || [];

    // Only a confirmed match may speak for the prescription. The upload
    // response still carries the matcher's closest guess on an unconfirmed
    // line (the history/DB shape nulls it out), and showing that guess's
    // name/strength/status here would present it as something the doctor
    // actually prescribed. The guess stays available as a guess - see
    // whyReason and guessedMedicine - but never as the row's identity.
    const confirmed = isConfirmedStatus(item.status) ? item.medicine : null;

    // Comparable alternatives (same pack quantity, real unflagged price, cheaper - the
    // backend's counts_for_savings) come first, then everything else by price. The
    // others stay listed, labelled, but are never presented as the saving.
    const safety = buildSafety(raw, item);

    // No substitute is offered for a medicine the patient reported an allergy to (the PDF
    // says the same: "Not shown: allergy alert").
    const alternatives = (safety.allergyAlert ? [] : priceEntry?.alternatives || [])
      .filter((a) => !a.is_discontinued)
      .slice()
      .sort((a, b) => (b.counts_for_savings ? 1 : 0) - (a.counts_for_savings ? 1 : 0) || (a.price ?? Infinity) - (b.price ?? Infinity));
    const topAlternative = alternatives.find((a) => a.counts_for_savings) || null;

    const referencePrice = priceEntry?.reference_price;
    const priceFlag = referencePrice?.price_flag || null;
    // The product on file for a generic-name line is one of many with that composition:
    // its price is not "the prescribed price", so nothing is compared against it.
    const prescribedPrice = referencePrice?.price_reliable && !safety.brandUnspecified ? referencePrice.price : null;
    const savingAmount =
      topAlternative && prescribedPrice != null && !priceFlag ? Math.max(0, prescribedPrice - topAlternative.price) : null;
    const savingPercent = savingAmount != null && topAlternative?.savings_percent > 0 ? topAlternative.savings_percent : null;
    const priceNote = safety.brandUnspecified
      ? "Brand not named"
      : safety.allergyAlert
        ? "Not shown: allergy alert"
        : priceFlag
        ? referencePrice.price_flag_note
        : null;

    const availability = confirmed?.is_discontinued
      ? { label: "Discontinued by manufacturer", tone: "error" }
      : { label: "Confirm with your pharmacy", tone: "muted" };

    return {
      id: pmId ?? `line-${index}`,
      rawText: item.raw_text,
      status: item.status,
      confidence: item.confidence,
      doctorMedicine: confirmed,
      guessedMedicine: isConfirmedStatus(item.status) ? null : item.medicine,
      medicineLabel: confirmed ? confirmed.medicine_name : item.raw_text,
      strength: confirmed?.strength || null,
      form: confirmed?.form || null,
      // The backend now parses these off the printed line. deriveFrequency
      // is the fallback for prescriptions processed before it did.
      dosage: raw.dosage || null,
      frequency: raw.frequency || deriveFrequency(item.raw_text),
      duration: raw.duration || null,
      topAlternative,
      allAlternatives: alternatives,
      recommendations,
      prescribedPrice,
      priceReliable: !!priceEntry?.reference_price?.price_reliable && !safety.brandUnspecified,
      priceFlag,
      priceNote,
      priceDate: priceEntry?.reference_price?.price_date || null,
      savingAmount,
      savingPercent,
      availability,
      ...safety,
      relevantFindings: confirmed
        ? findings.filter((f) => (f.medicines_involved || []).some((m) => m.medicine_id === confirmed.medicine_id))
        : [],
      whyReason: buildWhyReason(item, safety),
    };
  });
}
