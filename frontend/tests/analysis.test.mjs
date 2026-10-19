// Logic tests: does the analysis page say what the backend and the PDF say?
//
// The fixture (tests/fixtures/analysis.json) is a REAL backend response plus the figures
// the PDF report is built from, written by backend/tests/make_frontend_fixture.py.
//
//   npm run test:logic
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { buildDecisionRows, confidenceText, rowStatus, summarizeDetail, summarizeSavings } from "../.test-build/entry.js";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/analysis.json", import.meta.url), "utf8"));
const rows = buildDecisionRows(fixture.detail);
const byRaw = Object.fromEntries(rows.map((r) => [r.rawText, r]));
const pdfByRaw = Object.fromEntries(fixture.pdf.lines.map((l) => [l.raw_text, l]));

test("every detected line appears on screen and in the PDF", () => {
  assert.equal(rows.length, fixture.pdf.lines.length);
  for (const raw of Object.keys(pdfByRaw)) assert.ok(byRaw[raw], `${raw} missing from the screen`);
});

test("status wording on screen equals the PDF's", () => {
  for (const row of rows) assert.equal(rowStatus(row).text, pdfByRaw[row.rawText].status, row.rawText);
});

test("confidence wording on screen equals the PDF's", () => {
  for (const row of rows) assert.equal(confidenceText(row), pdfByRaw[row.rawText].confidence, row.rawText);
});

test("savings total on screen equals the PDF's, line by line and in sum", () => {
  const s = summarizeSavings(rows);
  assert.equal(Math.round(s.totalSaving * 100), Math.round(fixture.pdf.total_saving * 100));
  assert.equal(s.savableCount, fixture.pdf.counted_for_savings);
  for (const row of rows) {
    const pdfSaving = pdfByRaw[row.rawText].saving;
    const counted = summarizeSavings([row]).savableCount === 1; // the real rule, not a copy of it
    assert.equal(counted, pdfSaving != null, `${row.rawText}: screen ${counted} vs PDF ${pdfSaving}`);
    if (counted) assert.ok(Math.abs(row.savingAmount - pdfSaving) < 0.01, row.rawText);
  }
  assert.equal(summarizeDetail(fixture.detail).savings, s.totalSaving);
});

test("release type and composition come through, and match the PDF", () => {
  for (const row of rows) {
    const pdf = pdfByRaw[row.rawText];
    assert.equal(row.releaseLabel, pdf.release_label, row.rawText);
    if (row.doctorMedicine) assert.equal(row.doctorMedicine.composition, pdf.composition, row.rawText);
  }
  assert.equal(byRaw["Tab Metformin 500 SR"].releaseLabel, "sustained release");
  assert.equal(byRaw["Tab Metformin 500 SR"].doctorMedicine.release_type, "sr");
  assert.equal(byRaw["Tab Dolo 650"].releaseLabel, null);
});

test("allergy alerts are the same on screen and in the PDF, and never carry a saving", () => {
  for (const row of rows) {
    assert.equal(row.allergyAlert, pdfByRaw[row.rawText].allergy_alert, row.rawText);
    if (row.allergyAlert) assert.equal(summarizeSavings([row]).totalSaving, 0);
  }
  const flagged = byRaw["Tab Augmentin 625 Duo"];
  assert.equal(flagged.allergyAlert, true);
  // the PDF shows "Not shown: allergy alert": no substitute is suggested for it on screen either
  assert.equal(flagged.topAlternative, null);
  assert.equal(flagged.savingAmount, null);
  assert.equal(flagged.allAlternatives.length, 0);
  assert.equal(flagged.priceNote, "Not shown: allergy alert");
});

test("a line the OCR was unsure of is never shown as settled, on screen or in the PDF", () => {
  const row = byRaw["Tab Dolo 650"];
  assert.equal(pdfByRaw["Tab Dolo 650"].ocr_uncertain, true);
  assert.equal(row.ocrUncertain, true);
  assert.equal(rowStatus(row).text, "Check match");
  assert.equal(rowStatus(row).text, pdfByRaw["Tab Dolo 650"].status);
  assert.equal(row.verificationStatus, "flagged_for_review");
  assert.match(row.whyReason, /low confidence/);
  assert.equal(pdfByRaw["Tab Dolo 650"].saving, null); // and it earns no saving in the total
  assert.equal(summarizeDetail(fixture.detail).needsCheck >= 1, true);
  for (const other of rows.filter((r) => r.rawText !== "Tab Dolo 650")) assert.equal(other.ocrUncertain, false, other.rawText);
});

test("a line that needs a choice names no product, offers candidates and explains why", () => {
  for (const raw of ["Metformin", "Augmentin"]) {
    const row = byRaw[raw];
    assert.equal(row.doctorMedicine, null, raw);
    assert.equal(rowStatus(row).text, "Needs verification");
    assert.ok(row.needsDisambiguation && row.matchOptions.length >= 2, raw);
    assert.match(row.verificationReason, /does not say which/, raw);
    assert.match(row.whyReason, /choose the product/, raw);
    assert.match(confidenceText(row), /^\d+ possible products$/, raw);
    assert.equal(row.savingAmount, null);
  }
  const unsupported = byRaw["Nifedipine 30"];
  assert.equal(unsupported.doctorMedicine, null);
  assert.equal(unsupported.matchOptions.length, 0);
});

test("a generic-name line is flagged and gets no price or saving against one arbitrary brand", () => {
  const row = byRaw["Tab Paracetamol 650"];
  assert.equal(row.brandUnspecified, pdfByRaw["Tab Paracetamol 650"].brand_unspecified);
  assert.equal(row.brandUnspecified, true);
  assert.equal(row.prescribedPrice, null);
  assert.equal(row.savingAmount, null);
  assert.equal(row.priceNote, "Brand not named");
  assert.equal(byRaw["Tab Dolo 650"].brandUnspecified, false);
});

test("only comparable alternatives are presented as the saving", () => {
  for (const row of rows) {
    if (row.topAlternative) {
      assert.ok(row.topAlternative.counts_for_savings, row.rawText);
      assert.ok(row.topAlternative.same_pack_quantity, row.rawText);
      assert.equal(row.topAlternative.price_flag, null, row.rawText);
    }
    // comparable alternatives are listed before the rest
    const flags = row.allAlternatives.map((a) => a.counts_for_savings);
    assert.deepEqual(flags, [...flags].sort((a, b) => Number(b) - Number(a)), row.rawText);
  }
  // Telma 40 is a strip of 30; the strips of 10 stay listed but are labelled and not counted
  const telma = byRaw["Tab Telma 40"];
  assert.ok(telma.allAlternatives.some((a) => !a.same_pack_quantity));
  assert.ok(telma.allAlternatives.filter((a) => !a.same_pack_quantity).every((a) => !a.counts_for_savings && a.savings_percent == null));
  assert.ok(telma.topAlternative);
});

// ---- the review states (real decisions made through the real routes when the fixture was written) -------------------------
test("a match whose form differs from the line reads 'Check match' and earns no saving, on screen and in the PDF", () => {
  const row = byRaw["Cap Omez 20"];
  const pdf = pdfByRaw["Cap Omez 20"];
  assert.equal(row.formConflict, true);
  assert.equal(pdf.form_conflict, true);
  assert.equal(rowStatus(row).text, "Check match");
  assert.equal(pdf.status, "Check match");
  assert.equal(summarizeSavings([row]).savableCount, 0);
  assert.equal(pdf.saving, null);
  assert.equal(pdf.reason, "Not counted: check match first");
});

test("a product confirmed despite conflicts keeps the person's decision but earns no saving, on screen and in the PDF", () => {
  const row = byRaw["T Lincont 100"];
  const pdf = pdfByRaw["T Lincont 100"];
  assert.equal(rowStatus(row).text, "Confirmed");
  assert.equal(pdf.status, "Confirmed");
  assert.equal(confidenceText(row), "Confirmed by you");
  assert.equal(row.confirmedWithConflicts, true);
  assert.equal(pdf.confirmed_with_conflicts, true);
  assert.ok(row.confirmationConflicts.length >= 2);
  assert.equal(row.savingAmount != null, true, "the comparison itself is still shown");
  assert.equal(summarizeSavings([row]).savableCount, 0, "but it is not counted");
  assert.equal(pdf.saving, null);
  assert.equal(pdf.reason, "Not counted: confirmed despite differences from the line");
  assert.equal(row.doctorMedicine.medicine_name, "Zincold Syrup");
  assert.equal(row.rawText, "T Lincont 100");   // what was read is never replaced
});

test("a line the person marked not identified is the same on screen and in the PDF, unpriced and uncounted", () => {
  const row = byRaw["T Linogen XT"];
  const pdf = pdfByRaw["T Linogen XT"];
  assert.equal(rowStatus(row).text, "Not identified (by you)");
  assert.equal(pdf.status, "Not identified (by you)");
  assert.equal(confidenceText(row), "Marked by you");
  assert.equal(pdf.confidence, "Marked by you");
  assert.equal(row.doctorMedicine, null);
  assert.equal(row.prescribedPrice, null);
  assert.equal(pdf.saving, null);
  assert.equal(pdf.price, null);
});

test("an unsettled line offers its look-alikes as unconfirmed and is unpriced", () => {
  const row = byRaw["Tab Zincovit"];
  assert.equal(rowStatus(row).text, "Needs verification");
  assert.equal(pdfByRaw["Tab Zincovit"].status, "Needs verification");
  assert.ok(row.closestGuesses.length >= 1);
  assert.ok(row.verificationReasons.length >= 1);
  assert.equal(row.doctorMedicine, null);
  assert.equal(row.priceReliable, false);
  assert.equal(pdfByRaw["Tab Zincovit"].price, null);
});

test("every decision is kept per line, and only on the lines it was made on", () => {
  assert.deepEqual(byRaw["T Lincont 100"].verificationHistory.map((d) => d.decision), ["confirmed"]);
  assert.equal(byRaw["T Lincont 100"].verificationHistory[0].warnings_acknowledged, true);
  assert.deepEqual(byRaw["T Linogen XT"].verificationHistory.map((d) => d.decision), ["unmatched"]);
  for (const raw of ["Tab Dolo 650", "Cap Omez 20", "Tab Zincovit", "Metformin"]) assert.deepEqual(byRaw[raw].verificationHistory, [], raw);
});

test("the headline savings count only what the PDF counts", () => {
  const counted = rows.filter((r) => summarizeSavings([r]).savableCount === 1).map((r) => r.rawText);
  assert.deepEqual(counted.sort(), fixture.pdf.lines.filter((l) => l.saving != null).map((l) => l.raw_text).sort());
  for (const raw of ["Cap Omez 20", "T Lincont 100", "T Linogen XT", "Tab Zincovit", "Tab Dolo 650"]) assert.ok(!counted.includes(raw), raw);
});
