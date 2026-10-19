// A real handwritten prescription, as the analysis page receives it.
//
// tests/fixtures/handwritten.json is the REAL payload of GET /api/prescriptions/<id> for the prescription in
// backend/tests/test_handwritten_prescription.py (the captured Vision output run through the actual pipeline, written by
// backend/tests/make_handwritten_fixture.py). These tests check what the SCREEN does with it. They do not prove the handwriting was read
// correctly: four of its five brands are not in the dataset, so they stay unconfirmed.
//
//   npm run test:logic
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  AllergyNotice, Detail, EnterDetailsDialog, MemoryRouter, MedicineTable, PrescriptionNotes, STATUS_MEANINGS, StatusLegend, buildDecisionRows,
  confidenceText, detailsProblem, initialDetails, rowStatus, summarizeSavings,
} from "../.test-build/entry.js";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/handwritten.json", import.meta.url), "utf8"));
const rows = buildDecisionRows(fixture);
const by = (needle) => rows.find((r) => r.rawText.toLowerCase().includes(needle.toLowerCase()));
const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
const h = React.createElement;

test("five medicine lines, none confirmed, none matched", () => {
  assert.equal(rows.length, 5);
  for (const row of rows) {
    assert.equal(row.doctorMedicine, null, row.rawText);
    assert.notEqual(rowStatus(row).text, "Matched", row.rawText);
    assert.notEqual(rowStatus(row).text, "Confirmed", row.rawText);
  }
});

test("only the name that is in the dataset is Suggested; the rest say Needs verification", () => {
  const statuses = Object.fromEntries(rows.map((r) => [r.rawText, rowStatus(r).text]));
  assert.equal(statuses["T. pan - D 100"], "Suggested");
  for (const raw of ["T Lincont 100", "T shel cal soong 0-1-0", "Tap D - risl 60 k", "T. Linogen . XT"]) assert.equal(statuses[raw], "Needs verification", raw);
  assert.equal(by("pan").suggestion.medicine_name, "Pan-D Capsule PR");
});

test("an unconfirmed line carries no price, saving, alternative or safety-check claim", () => {
  for (const row of rows) {
    assert.equal(row.prescribedPrice, null, row.rawText);
    assert.equal(row.savingAmount, null, row.rawText);
    assert.equal(row.topAlternative, null, row.rawText);
    assert.equal(row.allAlternatives.length, 0, row.rawText);
    assert.equal(row.offers, null, row.rawText);
    assert.equal(row.allergyAlert, false, row.rawText);
    assert.equal(row.interactionShort, "Not checked yet", row.rawText);
    assert.deepEqual(row.relevantFindings, [], row.rawText);
  }
  const savings = summarizeSavings(rows);
  assert.equal(savings.totalSaving, 0);
  assert.equal(savings.savableCount, 0);
});

test("a look-alike is a candidate with a reason, and the confidence wording says it is a guess", () => {
  const lincont = by("lincont");
  assert.ok(lincont.closestGuesses.some((g) => g.medicine_name.includes("Lincer")));
  assert.ok(lincont.verificationReasons.join(" ").includes("not the same"));
  assert.match(confidenceText(lincont), /^Closest guess: \d+%$/);
  assert.match(lincont.whyReason, /look-alikes, not confirmed matches/);
});

test("a brand not in the dataset says so instead of inventing a candidate", () => {
  const rise = by("risl");
  assert.equal(rise.closestGuesses.length, 0);
  assert.match(rise.whyReason, /brand may not be in the dataset/);
  assert.equal(confidenceText(rise), "No match found");
});

test("schedules are shown as read: 0-1-0 written, 100 as a possible 1-0-0, once weekly, and nothing invented", () => {
  assert.equal(by("shel cal").instructions.schedule, "0-1-0");
  assert.equal(by("shel cal").instructions.schedule_certainty, "written");
  assert.equal(by("lincont").instructions.schedule_certainty, "digits_run_together");
  assert.match(by("lincont").instructions.text, /digits were read as/);
  assert.match(by("risl").instructions.text.toLowerCase(), /once weekly/);
  assert.equal(by("risl").instructions.duration, null);
  assert.equal(by("linogen").instructions.schedule, null);
  for (const row of rows) assert.equal(row.strength, null, `${row.rawText}: a schedule is never shown as a strength`);
});

test("the table shows the written text, the suggestion and no matched wording", () => {
  const html = renderToStaticMarkup(h(MemoryRouter, null, h(MedicineTable, { detail: fixture })));
  const out = text(html);
  for (const raw of ["T Lincont 100", "T shel cal soong 0-1-0", "Tap D - risl 60 k", "T. Linogen . XT", "T. pan - D 100"]) assert.ok(out.includes(raw), raw);
  assert.ok(out.includes("Suggested: Pan-D Capsule PR, not confirmed"));
  assert.ok(!out.includes("Matched"), "nothing here is matched");
  assert.equal((out.match(/Needs verification/g) || []).length, 4);
  assert.ok(!/₹/.test(out), "no price is shown for an unconfirmed line");
});

test("the suggested line's detail says it is not confirmed and offers no price or safety result", () => {
  const row = by("pan");
  const out = text(renderToStaticMarkup(h(Detail, { row, editable: true, onEdit() {}, onReviewGuess() {}, onMarkUnmatched() {}, onExplain() {} })));
  assert.match(out, /Suggested: Pan-D Capsule PR/);
  assert.match(out, /nothing is confirmed/);
  assert.ok(!/Save ₹|% lower/.test(out));
});

test("the status legend defines every word the table uses", () => {
  const out = text(renderToStaticMarkup(h(StatusLegend)));
  for (const word of ["Confirmed", "Matched", "Suggested", "Needs verification", "Entered by you"]) assert.ok(out.includes(word), word);
  assert.equal(STATUS_MEANINGS.length, 5);
  assert.match(out, /Nothing is priced or safety-checked until you confirm it/);
});

test("instructions and the Hindi note are listed apart from the medicines, with the reading marked as automatic", () => {
  const out = text(renderToStaticMarkup(h(PrescriptionNotes, { notes: fixture.notes })));
  assert.ok(out.includes("Other instructions on the prescription (not medicines)"));
  assert.ok(out.includes("#xillary temperature monitoring"));
  assert.ok(out.includes("Handwritten Hindi note, shown as read."));
  assert.ok(out.includes("Automatic reading, please check it: “morning, after food”"));
  assert.ok(out.includes("does not say which medicine it belongs to"));
  assert.equal(renderToStaticMarkup(h(PrescriptionNotes, { notes: [] })), "");
  assert.equal(renderToStaticMarkup(h(PrescriptionNotes, { notes: null })), "");
});

test("with no allergies saved the page says the check did not run, never that it passed", () => {
  const out = text(renderToStaticMarkup(h(AllergyNotice, { check: fixture.allergy_check })));
  assert.match(out, /Allergy check\. No allergies are saved on your account, so the allergy check did not run/);
  assert.match(out, /does NOT mean no allergy was found/);
  assert.ok(!/passed|no allergy found\b(?!\.)|safe/i.test(out.replace("does NOT mean no allergy was found", "")), out);
  assert.equal(renderToStaticMarkup(h(AllergyNotice, { check: null })), "");
  const declared = text(renderToStaticMarkup(h(AllergyNotice, { check: { declared: true, count: 1, message: "The allergy check compared the medicines you confirmed with the 1 allergy saved on your account." } })));
  assert.ok(declared.includes("compared the medicines you confirmed"));
});

test("the enter-details form starts empty, validates, and is clear about what it does", () => {
  assert.deepEqual(initialDetails(by("lincont")), { name: "", strength: "", form: "", schedule: "", duration: "" });
  const html = renderToStaticMarkup(h(EnterDetailsDialog, { open: true, rawText: "T Lincont 100", initial: initialDetails(by("lincont")), saving: false, error: "", onCancel() {}, onSave() {} }));
  const out = text(html);
  for (const label of ["Medicine name", "Strength (optional)", "Form (optional)", "Schedule (optional)", "Duration (optional)", "Save details"]) assert.ok(out.includes(label), label);
  assert.ok(out.includes("Read from your prescription: “T Lincont 100”"));
  assert.ok(out.includes("not matched to the medicine dataset"));
  assert.ok(out.includes("no price, saving, alternative or medicine-specific safety check"));
  assert.ok(html.includes('value=""'), "nothing is pre-filled from a guess");
  assert.equal(renderToStaticMarkup(h(EnterDetailsDialog, { open: false, rawText: "x", onCancel() {}, onSave() {} })), "");
});

test("details are validated like the server does", () => {
  assert.match(detailsProblem({ name: "" }), /Enter the medicine name/);
  assert.match(detailsProblem({ name: "a" }), /at least 2/);
  assert.match(detailsProblem({ name: "x".repeat(101) }), /at most 100/);
  assert.match(detailsProblem({ name: "Ok", strength: "9".repeat(41) }), /Strength must be at most 40/);
  assert.match(detailsProblem({ name: "Ok", schedule: "s".repeat(101) }), /Schedule must be at most 100/);
  assert.equal(detailsProblem({ name: "Zinconit", strength: "500 mg", form: "Tablet", schedule: "1-0-0", duration: "30 days" }), null);
});

test("a typed medicine is shown as Entered by you, with its details, and still has no price or safety check", () => {
  const typed = JSON.parse(JSON.stringify(fixture));
  const line = typed.detected_medicines.find((m) => m.raw_text.includes("shel cal"));
  line.match_status = "user_unmatched";
  line.verification_status = "entered_by_user";
  line.user_unmatched = true;
  line.suggested = false;
  line.user_entered = { name: "Shelcal Strong", strength: "500 mg", form: "Tablet", schedule: "0-1-0", duration: "30 days" };
  const row = buildDecisionRows(typed).find((r) => r.rawText.includes("shel cal"));
  assert.equal(rowStatus(row).text, "Entered by you");
  assert.equal(confidenceText(row), "Entered by you");
  assert.equal(row.medicineLabel, "Shelcal Strong");
  assert.equal(row.strength, "500 mg");
  assert.equal(row.form, "Tablet");
  assert.equal(row.prescribedPrice, null);
  assert.equal(row.savingAmount, null);
  assert.equal(row.doctorMedicine, null);
  assert.match(row.whyReason, /You entered "Shelcal Strong" yourself/);
  const out = text(renderToStaticMarkup(h(MemoryRouter, null, h(MedicineTable, { detail: typed }))));
  assert.ok(out.includes("Shelcal Strong"));
  assert.ok(out.includes("Read as “T shel cal soong 0-1-0”. Entered by you"));
  assert.ok(out.includes("500 mg · Tablet"));
  assert.equal((out.match(/Needs verification/g) || []).length, 3);
  // three lines were read with low confidence; the one the person typed in is no longer described that way
  const beforeTyping = text(renderToStaticMarkup(h(MemoryRouter, null, h(MedicineTable, { detail: fixture }))));
  assert.equal((beforeTyping.match(/Text read with low confidence/g) || []).length, 3);
  assert.equal((out.match(/Text read with low confidence/g) || []).length, 2);
});
