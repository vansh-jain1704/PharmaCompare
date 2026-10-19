// Shared shape-normalizers: the upload response and the prescription
// detail (history) response describe the same data slightly differently,
// since one comes straight from the matching engine and the other from a
// flat DB table join. These functions convert either into one consistent
// shape so components only ever handle one form.

export const MATCH_STATUS_META = {
  matched: { label: "Identified", className: "badge-success" },
  user_confirmed: { label: "Confirmed by you", className: "badge-success" },
  needs_verification: { label: "Needs verification", className: "badge-warning" },
  user_unmatched: { label: "Not identified (by you)", className: "badge-muted" },
};

// A line is settled either because the matcher was confident or because the
// user said so outright - the latter being the stronger of the two.
export function isConfirmedStatus(status) {
  return status === "matched" || status === "user_confirmed";
}

export function normalizeDetectedMedicine(row) {
  if ("status" in row) {
    // already the upload-response shape
    return row;
  }
  const hasMedicine = row.medicine_id != null;
  return {
    raw_text: row.raw_text,
    status: row.match_status,
    confidence: row.match_confidence != null ? parseFloat(row.match_confidence) : null,
    medicine: hasMedicine
      ? {
          medicine_id: row.medicine_id,
          medicine_name: row.medicine_name,
          composition: row.composition,
          form: row.form,
          strength: row.strength,
          manufacturer: row.manufacturer,
          // The history query returns these too; dropping them here made the
          // detail panel say "not on file" for fields that are on file.
          primary_salt: row.primary_salt,
          secondary_salt: row.secondary_salt,
          pack_size: row.pack_size,
          release_type: row.release_type ?? null,
          // a partial ingredient list is never a basis for searching the product (see utils/buyGeneric.js)
          composition_incomplete: !!row.composition_incomplete,
          price: row.price != null ? parseFloat(row.price) : null,
          is_discontinued: !!row.is_discontinued,
        }
      : null,
  };
}

export const SEVERITY_META = {
  Major: { label: "Major", className: "badge-error" },
  Moderate: { label: "Moderate", className: "badge-warning" },
  Minor: { label: "Minor", className: "badge-muted" },
  Unknown: { label: "Unknown severity", className: "badge-muted" },
  NEEDS_VERIFICATION: { label: "Needs verification", className: "badge-muted" },
};

export const ISSUE_TYPE_LABELS = {
  interaction: "Drug interaction",
  duplicate: "Duplicate medicine",
  dosage_inconsistency: "Dosage inconsistency",
  allergy_check: "Allergy check",
};

// Converts the flat Price_Comparison DB rows (history view) into the same
// nested { pm_id, prescribed_medicine, reference_price, alternatives }
// shape the upload response already returns, so PriceComparisonView only
// needs to know one shape.
export function normalizePriceComparison(rows) {
  if (!rows || rows.length === 0) return [];
  if ("prescribed_medicine" in rows[0]) {
    return rows; // already normalized (upload response shape)
  }

  const byPm = {};
  rows.forEach((row) => {
    if (!byPm[row.pm_id]) {
      byPm[row.pm_id] = {
        pm_id: row.pm_id,
        raw_text: row.raw_text,
        verification_status: "confirmed",
        prescribed_medicine: null,
        reference_price: null,
        alternatives: [],
      };
    }
    const entry = byPm[row.pm_id];
    const priceNum = parseFloat(row.price);

    if (row.row_type === "prescribed") {
      entry.prescribed_medicine = {
        medicine_id: row.medicine_id,
        medicine_name: row.medicine_name,
        manufacturer: row.manufacturer,
        strength: row.strength,
        form: row.form,
        pack_size: row.pack_size,
        is_discontinued: !!row.is_discontinued,
      };
      entry.reference_price = {
        price: priceNum,
        price_per_unit: row.price_per_unit != null ? parseFloat(row.price_per_unit) : null,
        price_reliable: priceNum > 0,
        price_flag: row.price_flag ?? null,
        price_flag_note: row.price_flag_note ?? null,
        data_source: row.data_source,
        price_date: row.price_date,
        price_basis: row.price_basis ?? null,
      };
    } else {
      entry.alternatives.push({
        medicine_id: row.medicine_id,
        medicine_name: row.medicine_name,
        manufacturer: row.manufacturer,
        strength: row.strength,
        form: row.form,
        pack_size: row.pack_size,
        price: priceNum,
        price_per_unit: row.price_per_unit != null ? parseFloat(row.price_per_unit) : null,
        price_difference: row.price_difference != null ? parseFloat(row.price_difference) : null,
        savings_percent: row.savings_percent != null ? parseFloat(row.savings_percent) : null,
        // Price-quality fields, derived by the backend (price_quality.py) so the screen
        // and the PDF apply one rule.
        same_pack_quantity: !!row.same_pack_quantity,
        price_flag: row.price_flag ?? null,
        price_flag_note: row.price_flag_note ?? null,
        counts_for_savings: !!row.counts_for_savings,
        is_discontinued: !!row.is_discontinued,
        data_source: row.data_source,
        price_basis: row.price_basis ?? null,
      });
    }
  });

  return Object.values(byPm);
}

// Both the upload response and the history endpoint already return
// Generic_Recommendations as a flat list with the same core fields
// (pm_id, generic_name, price_difference, confidence_score, reason,
// data_source) - this just groups them by pm_id and attaches the
// prescribed medicine's name (looked up from the already-normalized
// price comparison list) so each group can be labelled sensibly.
export function groupRecommendations(rows, priceComparisonItems) {
  if (!rows || rows.length === 0) return [];

  const nameByPmId = {};
  (priceComparisonItems || []).forEach((item) => {
    if (item.prescribed_medicine) {
      nameByPmId[item.pm_id] = item.prescribed_medicine.medicine_name;
    }
  });

  const byPm = {};
  rows.forEach((row) => {
    const entry = byPm[row.pm_id] || (byPm[row.pm_id] = {
      pm_id: row.pm_id,
      prescribedName: nameByPmId[row.pm_id] || null,
      recommendations: [],
    });
    entry.recommendations.push({
      generic_name: row.generic_name,
      price_difference: row.price_difference != null ? parseFloat(row.price_difference) : null,
      confidence_score: row.confidence_score != null ? parseFloat(row.confidence_score) : null,
      reason: row.reason,
      data_source: row.data_source,
    });
  });

  return Object.values(byPm);
}
