// The Medicine Timeline and the dosing wording on screen: what the backend read from the prescription is shown as read,
// uncertain readings stay marked as uncertain, and nothing is defaulted.
//
//   npm run test:logic
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Detail, MedicineTimeline, buildDecisionRows, dosingSentence } from "../.test-build/entry.js";

const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
const render = (timeline) => text(renderToStaticMarkup(React.createElement(MedicineTimeline, { timeline })));
const MIDDLE_DOT = String.fromCharCode(183);
const LQ = String.fromCharCode(8220);
const RQ = String.fromCharCode(8221);

const item = (over = {}) => ({ pm_id: 1, medicine: "Dolo 650 Tablet", amount: "1 tablet", timing: "after food", duration: "for 5 days", possible: false, schedule: "1-0-1", source_text: "Tab Dolo 650 1-0-1", ...over });
const detail = (...lines) => ({ detected_medicines: lines, price_comparison: [], recommendations: [], clinical_analysis: { findings: [] } });

test("times of day are shown with each medicine's amount, timing and duration", () => {
  const out = render({
    slots: [{ slot: "morning", label: "Morning", items: [item()] }, { slot: "night", label: "Night", items: [item()] }],
    groups: [], not_identified: [], has_content: true,
  });
  assert.match(out, /Morning/);
  assert.match(out, /Night/);
  assert.match(out, /Dolo 650 Tablet/);
  assert.ok(out.includes(`1 tablet ${MIDDLE_DOT} after food`));
  assert.match(out, /for 5 days/);
  assert.match(out, /Nothing here is a dosing recommendation/);
});

test("a schedule that was only possibly read is marked possible, never stated as fact", () => {
  const out = render({ slots: [{ slot: "morning", label: "Morning", items: [item({ possible: true, schedule: "1-0-0" })] }], groups: [], not_identified: [], has_content: true });
  assert.match(out, /Possible schedule 1-0-0/);
});

test("what was not written is said, not filled in", () => {
  const out = render({ slots: [{ slot: "morning", label: "Morning", items: [item({ amount: null, timing: null, duration: "duration not written" })] }], groups: [], not_identified: [], has_content: true });
  assert.match(out, /amount not written/);
  assert.match(out, /duration not written/);
});

test("groups for as-needed, weekly and time-not-written medicines are shown under their own headings", () => {
  const out = render({
    slots: [], not_identified: [], has_content: true,
    groups: [
      { group: "as_needed", label: "Only when needed", items: [item({ medicine: "Dolo 650 Tablet", amount: null, timing: null, duration: "duration not written" })] },
      { group: "weekly", label: "Once a week", items: [item({ medicine: "D3 60K Capsule", duration: "for 8 weeks" })] },
      { group: "time_not_written", label: "Time of day not written", items: [item({ medicine: "Telma 40 Tablet", frequency: "Once daily", amount: null, timing: null })] },
    ],
  });
  for (const needle of ["Only when needed", "Once a week", "Time of day not written", "D3 60K Capsule", "for 8 weeks", "Once daily"]) assert.ok(out.includes(needle), needle);
});

test("a line that is not identified is listed apart from the timeline and keeps its caveat", () => {
  const out = render({
    slots: [], groups: [], has_content: true,
    not_identified: [{ pm_id: 3, source_text: "T Lincont 100", read_as: "possibly 1-0-0", duration: "for 30 days", possible: true }],
  });
  assert.match(out, /Not in the timeline until identified/);
  assert.match(out, /T Lincont 100/);
  assert.match(out, /only possibly a schedule/);
  assert.doesNotMatch(out, /Morning/);
});

test("with no dosing read the timeline says so instead of showing an empty or invented one", () => {
  for (const timeline of [null, undefined, { slots: [], groups: [], not_identified: [], has_content: false }]) {
    const out = render(timeline);
    assert.match(out, /No dosing instructions/);
    assert.match(out, /Nothing is assumed/);
  }
});

test("the one-sentence dosing reading keeps possible and unreadable wording", () => {
  assert.equal(dosingSentence(null), null);
  assert.equal(dosingSentence({}), null);
  assert.equal(
    dosingSentence({ text: "1-0-1: morning and night", dose: "1 tablet", timing: "after food", duration: "5 days" }),
    `1-0-1: morning and night ${MIDDLE_DOT} 1 tablet, after food ${MIDDLE_DOT} for 5 days`,
  );
  assert.match(dosingSentence({ text: `possibly 1-0-0 (the digits were read as ${LQ}100${RQ}; check the prescription)`, duration: "30 days" }), /^possibly 1-0-0/);
  assert.equal(dosingSentence({ frequency: "Once weekly", duration_unreadable: true }), `Once weekly ${MIDDLE_DOT} number of days could not be read`);
});

test("a row's detail shows 'Dosing (as written)' for an identified line and the reading for an unidentified one", () => {
  const base = { pm_id: 1, raw_text: "Tab Dolo 650", match_confidence: "1.0000", closest_guesses: [], verification_reasons: ["No product on file resembles this text."],
    instructions: { text: "1-0-1: morning and night", duration: "5 days", dose: "1 tablet", timing: "after food" } };
  const matched = { match_status: "matched", medicine_id: 5, medicine_name: "Dolo 650 Tablet", composition: "Paracetamol (650mg)", form: "Tablet", strength: "650mg", price: "34.27" };
  const props = { editable: false, saving: false, busy: false };
  const show = (line) => text(renderToStaticMarkup(React.createElement(Detail, { row: buildDecisionRows(detail(line))[0], ...props })));

  assert.ok(show({ ...base, ...matched }).includes(`Dosing (as written) 1-0-1: morning and night ${MIDDLE_DOT} 1 tablet, after food ${MIDDLE_DOT} for 5 days`));
  assert.match(show({ ...base, match_status: "needs_verification", medicine_id: null }), /Dosing read from this line: 1-0-1: morning and night/);
  assert.match(show({ ...base, ...matched, instructions: null }), /Dosing \(as written\) Not written/);
});

test("the analysis page shows the timeline under the medicines table", () => {
  const page = readFileSync(new URL("../src/pages/PrescriptionReport.jsx", import.meta.url), "utf8");
  assert.match(page, /<MedicineTimeline timeline=\{detail\.timeline\} \/>/);
  assert.ok(page.indexOf("<MedicineTable") < page.indexOf("<MedicineTimeline"), "the timeline comes after the table");
});

test("a combination product shows every ingredient's strength, falling back to the stored strength", () => {
  const combo = buildDecisionRows(detail({
    pm_id: 1, raw_text: "Pan-D", match_status: "user_confirmed", match_confidence: null, medicine_id: 9, medicine_name: "Pan-D Capsule PR",
    composition: "Domperidone (30mg) + Pantoprazole (40mg)", form: "Capsule", strength: "30mg", display_strength: "Domperidone 30mg + Pantoprazole 40mg",
    closest_guesses: [], verification_reasons: [],
  }))[0];
  assert.equal(combo.strength, "Domperidone 30mg + Pantoprazole 40mg");
  const older = buildDecisionRows(detail({
    pm_id: 1, raw_text: "Dolo", match_status: "matched", match_confidence: "1", medicine_id: 9, medicine_name: "Dolo 650 Tablet",
    composition: "Paracetamol (650mg)", form: "Tablet", strength: "650mg", closest_guesses: [], verification_reasons: [],
  }))[0];
  assert.equal(older.strength, "650mg");
});
