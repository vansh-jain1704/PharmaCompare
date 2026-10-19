import { buildDecisionRows, summarizeSavings } from "./decisionTable";

/**
 * One prescription, boiled down to the numbers the dashboard, history and
 * report header show. Everything comes from the same rows the table renders,
 * so a summary can never disagree with the analysis it links to.
 *
 *   detected          every line read from the prescription
 *   autoMatched       lines the matcher confirmed on its own
 *   userConfirmed     lines the person confirmed by hand
 *   needsVerification lines the matcher could not settle
 */
export function summarizeDetail(detail) {
  const rows = buildDecisionRows(detail || {});
  const savings = summarizeSavings(rows);
  const names = rows.map((r) => r.doctorMedicine?.medicine_name).filter(Boolean);
  return {
    detected: rows.length,
    identified: rows.filter((r) => r.doctorMedicine).length,
    autoMatched: rows.filter((r) => r.status === "matched").length,
    userConfirmed: rows.filter((r) => r.status === "user_confirmed").length,
    // a line the person reviewed and marked "not identified" has been decided: it no longer waits on them
    needsVerification: rows.filter((r) => !r.doctorMedicine && !r.userUnmatched).length,
    markedUnidentified: rows.filter((r) => r.userUnmatched).length,
    needsCheck: rows.filter((r) => r.doctorMedicine && (r.needsDisambiguation || r.ocrUncertain || r.needsCheck)).length,
    allergyAlerts: rows.filter((r) => r.allergyAlert).length,
    savings: savings.totalSaving || 0,
    savingsPercent: savings.percent,
    savingsCovered: savings.savableCount,
    names,
  };
}
