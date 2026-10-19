// The "Needs verification" review flow on the screen: what an unsettled line shows (the text as read, the
// look-alikes, why it was not accepted), how a conflicting choice is put to the person, and the rule that
// nothing is confirmed, priced or counted until the person decides.
//
//   npm run test:logic
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  ConfirmWarningsDialog, Detail, MedicinePickerDialog, MedicineTable,
  buildDecisionRows, confidenceText, rowStatus, summarizeDetail,
} from "../.test-build/entry.js";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

const GUESSES = [
  {
    medicine_id: 1, medicine_name: "Lincer 100mg Tablet", composition: "Sertraline (100mg)", strength: "100mg", form: "Tablet",
    manufacturer: "Acme", release_type: null, score: 0.8174,
    reasons: ["The name as read is only similar to this product, not the same."],
  },
  {
    medicine_id: 2, medicine_name: "Lincol 100mg Dry Syrup", composition: "Clindamycin (100mg)", strength: "100mg", form: "Syrup",
    manufacturer: null, release_type: "sr", score: 0.65, reasons: ["The name as read is only similar to this product, not the same."],
  },
];
const REASONS = [
  "The name as read is only similar to this product, not the same. The text may have been misread, or the brand may not be in the dataset.",
  "The similarity (82%) is below the 90% needed to accept a look-alike without a person checking.",
  "The text of this line was read with low confidence (63%), so it may not say what is written on the prescription.",
];

// a stored line as the prescription detail endpoint returns it (flat DB columns + the derived verification fields)
const line = (over = {}) => ({
  pm_id: 11, raw_text: "T Lincont 100", match_status: "needs_verification", match_confidence: "0.8174", medicine_id: null,
  interaction_status: "interaction_data_not_available", interaction_label: "Not checked", verification_status: "pending_verification",
  verification_label: "Not identified yet – only look-alike products were found.", verification_reason: null,
  verification_reasons: REASONS, closest_guesses: GUESSES, user_unmatched: false, needs_disambiguation: false, match_options: [],
  allergy_alert: false, ocr_uncertain: false, ocr_confidence: 0.63, brand_unspecified: false, verification_decision: null,
  ...over,
});
const detail = (...lines) => ({ detected_medicines: lines, price_comparison: [], recommendations: [], clinical_analysis: { findings: [] } });
const rowOf = (over) => buildDecisionRows(detail(line(over)))[0];

const renderDetail = (row, props = {}) =>
  renderToStaticMarkup(React.createElement(Detail, { row, editable: true, saving: false, busy: false, onReviewGuess() {}, onEdit() {}, onMarkUnmatched() {}, ...props }));

// ---- the row ------------------------------------------------------------------------------------------------------
test("an unsettled line keeps what was read, offers look-alikes as unconfirmed, and is never presented as identified", () => {
  const row = rowOf();
  assert.equal(row.rawText, "T Lincont 100");
  assert.equal(row.doctorMedicine, null);                 // nothing is the line's identity yet
  assert.equal(row.strength, null);
  assert.equal(row.form, null);
  assert.equal(row.closestGuesses.length, 2);
  assert.equal(row.verificationReasons.length, 3);
  assert.deepEqual(rowStatus(row), { tone: "warn", text: "Needs verification" });
  assert.equal(confidenceText(row), "Closest guess: 82%");
  assert.equal(row.savingAmount, null);
  assert.equal(row.priceReliable, false);
  assert.equal(row.prescribedPrice, null);
});

test("the explanation says why, names the look-alikes as not confirmed and offers both ways forward", () => {
  const why = rowOf().whyReason;
  assert.match(why, /could not be matched with enough certainty/);
  assert.match(why, /only similar/);
  assert.match(why, /look-alikes, not confirmed matches/);
  assert.match(why, /mark the line as not identified/);
});

test("a line with no candidates still explains itself", () => {
  const row = rowOf({ closest_guesses: [], verification_reasons: ["No product on file resembles this text. It may have been misread, or the brand may not be in the dataset."], match_confidence: null });
  assert.match(row.whyReason, /No medicine in our database matched/);
  assert.match(row.whyReason, /may have been misread/);
  assert.equal(confidenceText(row), "No match found");
});

test("a line the person marked 'not identified' is a decided state: visible, explained, and out of every analysis", () => {
  const row = rowOf({
    match_status: "user_unmatched", user_unmatched: true, verification_status: "marked_unidentified", verification_reasons: [],
    verification_decision: { decision: "unmatched", decided_at: "2026-10-18T10:15:00", warnings_acknowledged: false },
  });
  assert.deepEqual(rowStatus(row), { tone: "muted", text: "Not identified (by you)" });
  assert.equal(confidenceText(row), "Marked by you");
  assert.equal(row.doctorMedicine, null);
  assert.match(row.whyReason, /marked it as not identified/);
  assert.match(row.whyReason, /not part of the safety, price or savings checks/);
});

test("counts: a line marked not identified no longer waits on the person, and is counted on its own", () => {
  const summary = summarizeDetail(detail(
    line({ pm_id: 1 }),
    line({ pm_id: 2, match_status: "user_unmatched", user_unmatched: true, verification_status: "marked_unidentified" }),
  ));
  assert.equal(summary.detected, 2);
  assert.equal(summary.needsVerification, 1);
  assert.equal(summary.markedUnidentified, 1);
  assert.equal(summary.identified, 0);
  assert.equal(summary.savings, 0);
});

test("a matched line whose written form differs from the product reads 'Check match' and is held out of the savings total", () => {
  const matched = {
    match_status: "matched", match_confidence: "0.7441", medicine_id: 5, medicine_name: "Omez FF 20 Tablet", composition: "Omeprazole (20mg)",
    form: "Tablet", strength: "20mg", price: "100.00", raw_text: "Cap Omez 20 1-0-0", closest_guesses: [], verification_reasons: [],
    verification_status: "flagged_for_review", verification_label: "Flagged for review: the prescription points to a capsule but the matched product is a tablet.",
  };
  const flagged = buildDecisionRows(detail(line({ ...matched, form_conflict: true })))[0];
  const clean = buildDecisionRows(detail(line({ ...matched, form_conflict: false })))[0];
  assert.deepEqual(rowStatus(flagged), { tone: "warn", text: "Check match" });
  assert.deepEqual(rowStatus(clean), { tone: "ok", text: "Matched" });
  assert.equal(summarizeDetail(detail(line({ ...matched, form_conflict: true }))).needsCheck, 1);
  assert.equal(summarizeDetail(detail(line({ ...matched, form_conflict: false }))).needsCheck, 0);
  const html = renderToStaticMarkup(React.createElement(MedicineTable, { detail: detail(line({ ...matched, form_conflict: true })), prescriptionId: 5, onCorrected() {} }));
  assert.match(text(html), /Form differs from the prescription/);
});

// ---- the opened detail ----------------------------------------------------------------------------------------------
test("the opened line shows the text as read, why, each look-alike with its details and similarity, and the actions", () => {
  const out = text(renderDetail(rowOf()));
  assert.match(out, /Why this needs verification/);
  assert.match(out, /Read from your prescription as T Lincont 100/);
  assert.match(out, /text read with 63% confidence/);
  assert.match(out, /Closest look-alikes \(not confirmed\)/);
  for (const needle of ["Lincer 100mg Tablet", "Sertraline (100mg)", "100mg · Tablet", "Similarity 82%",
    "Lincol 100mg Dry Syrup", "100mg · Syrup · sustained release", "Similarity 65%"]) {
    assert.ok(out.includes(needle), `missing: ${needle}`);
  }
  assert.equal((out.match(/Review this/g) || []).length, 2);
  assert.match(out, /Verify/);
  assert.match(out, /None of these - mark as not identified/);
  assert.doesNotMatch(out, /Confirm this match/);        // nothing is offered as already matched
});

test("a read-only view offers no way to decide", () => {
  const out = text(renderDetail(rowOf(), { editable: false }));
  assert.doesNotMatch(out, /Review this|Verify|None of these/);
  assert.match(out, /Closest look-alikes \(not confirmed\)/);   // but the information is still there
});

test("a line marked not identified can be reviewed again, and no longer offers 'none of these'", () => {
  const out = text(renderDetail(rowOf({ match_status: "user_unmatched", user_unmatched: true, verification_status: "marked_unidentified",
    verification_decision: { decision: "unmatched", decided_at: "2026-10-18T10:15:00", warnings_acknowledged: false } })));
  assert.match(out, /Review again/);
  assert.doesNotMatch(out, /None of these/);
  assert.match(out, /you marked this line as not identified/);
  assert.match(out, /Your original line is kept as read: T Lincont 100/);
});

test("a line the person confirmed shows what they decided, keeps the original text, and never claims equivalence", () => {
  const row = rowOf({
    match_status: "user_confirmed", medicine_id: 246908, medicine_name: "Zincold Syrup", composition: "Chlorpheniramine Maleate (1mg/5ml) + Paracetamol (125mg/5ml)",
    form: "Syrup", strength: "1mg/5ml", price: "82.00", verification_status: "verified_by_user", closest_guesses: [], verification_reasons: [],
    verification_decision: { decision: "confirmed", decided_at: "2026-10-18T10:15:00", medicine_name: "Zincold Syrup", warnings_acknowledged: true },
  });
  const out = text(renderDetail(row));
  assert.match(out, /Your decision/);
  assert.match(out, /You chose Zincold Syrup for the line (?:"|&quot;)T Lincont 100/);
  assert.match(out, /You were shown differences between the prescription line and this product before you confirmed/);
  assert.doesNotMatch(out, /was matched to|matching our records|based on the medicine name/);   // nothing claims the system matched it
  assert.match(out, /you confirmed Zincold Syrup, after being shown differences from the prescription line/);
  assert.match(out, /Your original line is kept as read: T Lincont 100/);
  assert.match(out, /PharmaCompare has not verified that it is the one written on the prescription, or that it is medically equivalent/);
  assert.doesNotMatch(out, /Confirm this match/);
});

// ---- the table row -----------------------------------------------------------------------------------------------
test("the table row shows status, the look-alike as unconfirmed, a reason, and honest unavailable states", () => {
  const html = renderToStaticMarkup(React.createElement(MedicineTable, { detail: detail(line()), prescriptionId: 5, onCorrected() {} }));
  const out = text(html);
  assert.match(out, /Needs verification/);
  assert.match(out, /Closest guess: 82%/);
  assert.match(out, /Only look-alike products found/);
  assert.match(out, /Closest look-alike, not confirmed: Lincer 100mg Tablet/);
  assert.match(out, /Text read with low confidence/);
  assert.match(out, /Needs confirmation/);               // strength / form
  assert.match(out, /Identify the medicine first/);      // price and savings: because the line is not identified
  assert.doesNotMatch(out, /Price not available|Not available/);
  assert.match(out, /Verify/);
});

test("a line marked not identified reads as decided, not as missing data", () => {
  const html = renderToStaticMarkup(React.createElement(MedicineTable, {
    detail: detail(line({ match_status: "user_unmatched", user_unmatched: true, verification_status: "marked_unidentified" })),
    prescriptionId: 5, onCorrected() {},
  }));
  const out = text(html);
  assert.match(out, /Not identified \(by you\)/);
  assert.match(out, /Marked by you/);
  assert.match(out, /Review again/);
  assert.doesNotMatch(out, /Identify the medicine first|Needs confirmation/);
});

// ---- the warnings ----------------------------------------------------------------------------------------------------
const WARNINGS = [
  { code: "name", severity: "conflict", text: "The prescription line reads “T Lincont 100”, which does not look like “Zincold Syrup”." },
  { code: "form", severity: "conflict", text: "The prescription line points to a tablet, but “Zincold Syrup” is a syrup." },
  { code: "discontinued", severity: "note", text: "The dataset marks this product as discontinued." },
];
const renderWarnings = (props = {}) =>
  renderToStaticMarkup(React.createElement(ConfirmWarningsDialog, { open: true, rawText: "T Lincont 100", medicineName: "Zincold Syrup", warnings: WARNINGS, saving: false, onBack() {}, onConfirmAnyway() {}, ...props }));

test("the conflict dialog puts the line and the choice side by side, lists every difference, and never claims equivalence", () => {
  const out = text(renderWarnings());
  assert.match(out, /Check this before you confirm/);
  assert.match(out, /reads “T Lincont 100” and you chose “Zincold Syrup”/);
  assert.match(out, /does not look like “Zincold Syrup”/);
  assert.match(out, /points to a tablet, but “Zincold Syrup” is a syrup/);
  assert.match(out, /discontinued/);
  assert.match(out, /has not verified that this product matches the prescription or that it is medically equivalent/);
  assert.match(out, /Go back/);
  assert.match(out, /Confirm anyway — I checked my prescription/);
});

test("the conflict dialog is hidden when there is nothing to acknowledge and locks while saving", () => {
  assert.equal(renderWarnings({ open: false }), "");
  const html = renderWarnings({ saving: true });
  assert.match(html, /disabled/);
  assert.match(text(html), /Saving/);
});

// ---- the picker's part -------------------------------------------------------------------------------------------------
const renderPicker = (props = {}) =>
  renderToStaticMarkup(React.createElement(MedicinePickerDialog, { open: true, rawText: "T Lincont 100", suggestions: GUESSES, saving: false, onCancel() {}, onConfirm() {}, ...props }));

test("Verify opens with the reasons and the stored look-alikes, nothing selected, and the plain statement about confirming", () => {
  const html = renderPicker({ reasons: REASONS });
  const out = text(html);
  assert.match(out, /Why this line needs your check/);
  for (const reason of REASONS) assert.ok(out.includes(reason.replace(/\s+/g, " ")), reason);
  assert.match(out, /Suggested for this line \(not confirmed\)/);
  assert.match(out, /Lincer 100mg Tablet/);
  assert.equal((html.match(/aria-pressed="true"/g) || []).length, 0);
  assert.match(out, /does not prove that this is the medicine on your prescription, or that it is medically equivalent/);
  assert.match(html.match(/<button[^>]*>\s*Confirm medicine\s*<\/button>/)?.[0] || "", /disabled/);
});

test("'None of these' appears only when there is a line to decide about and a handler to call", () => {
  assert.match(text(renderPicker({ onMarkUnmatched() {} })), /None of these/);
  assert.doesNotMatch(text(renderPicker()), /None of these/);                                   // no handler
  assert.doesNotMatch(text(renderPicker({ rawText: "", onMarkUnmatched() {} })), /None of these/); // adding by hand
});

// ---- source guards: where a decision can come from -------------------------------------------------------------------------
test("nothing is confirmed or marked except through the person's own button presses", () => {
  const table = read("../src/components/results/MedicineTable.jsx");
  const picker = read("../src/components/MedicinePickerDialog.jsx");
  const dialog = read("../src/components/ConfirmWarningsDialog.jsx");
  const api = read("../src/api/prescriptionApi.js");

  // acknowledging is sent exactly once, from the explicit "Confirm anyway" button, never on a first attempt
  assert.equal((table.match(/confirmMedicine\(conflict\.medicine, conflict\.row, true\)/g) || []).length, 1);
  assert.match(table, /acknowledge = false/);
  assert.match(api, /acknowledgeWarnings = false/);
  assert.match(api, /acknowledgeWarnings \? \{ acknowledge_warnings: true \} : \{\}/);
  // only a 409 carrying warnings opens the dialog; every other failure is an ordinary error message
  assert.match(table, /err\?\.response\?\.status === 409/);
  // the picker can call onConfirm in one place only, and onMarkUnmatched only from its own button
  assert.equal((picker.match(/onConfirm\(/g) || []).length, 1);
  assert.equal((picker.match(/onMarkUnmatched\(\)/g) || []).length, 1);
  // the warnings dialog decides nothing by itself
  assert.doesNotMatch(dialog, /useEffect|setTimeout/);
  assert.equal((dialog.match(/onConfirmAnyway/g) || []).length, 2);   // the prop and its one button
});

test("no screen or report text calls a manual confirmation proof of equivalence", () => {
  for (const file of ["../src/components/results/MedicineTable.jsx", "../src/components/ConfirmWarningsDialog.jsx", "../src/components/MedicinePickerDialog.jsx"]) {
    const source = read(file);
    assert.doesNotMatch(source, /verified equivalent|guaranteed|clinically equivalent|safe to substitute/i, file);
  }
});

test("an idle dialog never claims to be searching", () => {
  const picker = read("../src/components/MedicinePickerDialog.jsx");
  assert.match(picker, /term\.length < 2\) \{[^}]*setLoading\(false\)/);   // empty query: not loading
  assert.match(picker, /setError\(""\);\s*setFallbackNote\(""\);\s*setLoading\(false\);/);   // fresh open: not loading
});
