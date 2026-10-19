// Objectives 1, 4 and 6 on screen: where a price comes from (and that it is never live), the live-feed status, data notes on a product, the data
// sources with their freshness, and the outside services. The wording is the server's; these tests check that the screens carry it through
// and never turn a reference price, an old snapshot or a missing feed into something that reads as live.
//
//   npm run test:logic
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { DataNotes, DataSourcesList, Detail, ExternalServices, MedicineTable, MemoryRouter, PriceSources, buildDecisionRows, hasWarning, normalizePriceComparison } from "../.test-build/entry.js";

const h = React.createElement;
const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
const fixture = JSON.parse(readFileSync(new URL("./fixtures/analysis.json", import.meta.url), "utf8"));

const BASIS = {
  basis: "reference_dataset", live: false, source_key: "indian_medicine_dataset", source_name: "Indian Medicine Dataset (community project on GitHub)",
  imported_on: "2026-10-12", age_days: 6, stale: false,
  what_the_date_means: "the day this snapshot was imported here; the source does not say when each price was true",
  label: "Reference price from the Indian Medicine Dataset (community project on GitHub), imported 12 Oct 2026 (6 days ago). Not a live price.",
};
const NO_FEED = { live_feed_connected: false, feeds: 0, pharmacies: 0, reports: 0, statement: "No live pharmacy price or stock feed is connected. Every price shown is a reference price from a dataset snapshot, and no stock level is known." };
const FEED = { live_feed_connected: true, feeds: 1, pharmacies: 2, reports: 5, statement: "1 pharmacy feed (2 pharmacies) have reported 5 price or stock observations; the latest was observed 18 Oct 2026, 10:00. These are shown separately from reference prices, with their age. They are reports, not a live connection to a pharmacy." };

// ---- Objective 1: prices ---------------------------------------------------------------------------------------------------------

test("a reference price is labelled with its source, its import date and that it is not live; the date is never called a validity date", () => {
  const out = text(renderToStaticMarkup(h(PriceSources, { basis: BASIS, live: null })));
  assert.ok(out.includes("Reference price · not live"));
  assert.ok(out.includes("imported 12 Oct 2026 (6 days ago). Not a live price."));
  assert.ok(out.includes("The date is the day this snapshot was imported here; the source does not say when each price was true."));
  assert.ok(!/valid on|as of|current price/i.test(out));
});

test("with no feed the page says no live feed is connected; with one it still says reports, never live", () => {
  const none = text(renderToStaticMarkup(h(PriceSources, { basis: BASIS, live: NO_FEED })));
  assert.ok(none.includes("No live feed connected"));
  assert.ok(none.includes("No live pharmacy price or stock feed is connected."));
  assert.ok(none.includes("no stock level is known"));
  const some = renderToStaticMarkup(h(PriceSources, { basis: BASIS, live: FEED }));
  assert.ok(text(some).includes("Pharmacy reports received"));
  assert.ok(text(some).includes("They are reports, not a live connection to a pharmacy."));
  assert.ok(some.includes("is-ok"));
  assert.ok(!text(some).includes("No live feed connected"));
});

test("nothing is rendered when the server sent neither statement", () => {
  assert.equal(renderToStaticMarkup(h(PriceSources, { basis: null, live: null })), "");
});

test("the normaliser carries the provenance of the reference price and of each alternative through", () => {
  const rows = [
    { pm_id: 1, row_type: "prescribed", medicine_id: 10, medicine_name: "A", price: "50.00", price_date: "2026-10-12T10:00:00", data_source: "x", price_basis: BASIS, is_discontinued: 0 },
    { pm_id: 1, row_type: "alternative", medicine_id: 11, medicine_name: "B", price: "30.00", price_date: "2026-10-12T10:00:00", data_source: "x", price_basis: BASIS, is_discontinued: 0, same_pack_quantity: 1 },
    { pm_id: 2, row_type: "prescribed", medicine_id: 12, medicine_name: "C", price: "20.00", price_date: null, data_source: "x", is_discontinued: 0 },
  ];
  const [one, two] = normalizePriceComparison(rows);
  assert.deepEqual(one.reference_price.price_basis, BASIS);
  assert.deepEqual(one.alternatives[0].price_basis, BASIS);
  assert.equal(two.reference_price.price_basis, null, "an old payload without it is not given an invented one");
});

function pricedRow(withBasis) {
  const detail = JSON.parse(JSON.stringify(fixture.detail));
  const rows = buildDecisionRows(detail);
  const target = rows.find((r) => r.doctorMedicine && r.priceReliable);
  assert.ok(target, "the fixture has a priced, matched line");
  if (withBasis) detail.price_comparison.forEach((p) => { if (p.pm_id === target.id) p.price_basis = BASIS; });
  return buildDecisionRows(detail).find((r) => r.id === target.id);
}

test("a priced line's detail states the provenance of its reference price, and falls back to a plain not-live statement", () => {
  const props = { editable: false, onEdit() {}, onReviewGuess() {}, onMarkUnmatched() {}, onExplain() {} };
  const withBasis = pricedRow(true);
  assert.deepEqual(withBasis.priceBasis, BASIS);
  assert.ok(text(renderToStaticMarkup(h(Detail, { row: withBasis, ...props }))).includes(BASIS.label));
  const without = pricedRow(false);
  assert.equal(without.priceBasis, null);
  assert.ok(text(renderToStaticMarkup(h(Detail, { row: without, ...props }))).includes("Reference price from a dataset snapshot. Not a live price."));
});

test("the medicines table ends with where the prices come from and whether any live feed exists", () => {
  const detail = { ...fixture.detail, price_basis: BASIS, live_data: NO_FEED };
  const out = text(renderToStaticMarkup(h(MemoryRouter, null, h(MedicineTable, { detail }))));
  assert.ok(out.includes("Prices are reference-dataset figures, not live pharmacy prices."));
  assert.ok(out.includes(BASIS.label));
  assert.ok(out.includes("No live pharmacy price or stock feed is connected."));
});

// ---- Objective 6: data notes -----------------------------------------------------------------------------------------------------

const NOTES = [
  { code: "strength_not_in_composition", level: "warn", text: "The strength in the name could not be matched to the ingredient strengths on record (it may be written another way, such as a % or a per-ml concentration). Check it against the pack." },
  { code: "no_pack_size", level: "info", text: "No pack size is on record, so prices cannot be compared per unit." },
];

test("data notes are shown as a reason to check, never as a correction, with warnings marked", () => {
  const html = renderToStaticMarkup(h(DataNotes, { notes: NOTES }));
  const out = text(html);
  assert.ok(out.includes("Data notes (a reason to check the pack, not a correction)"));
  for (const n of NOTES) assert.ok(out.includes(n.text));
  assert.ok(html.includes("warn-text") && html.includes("small muted"));
  assert.ok(!/wrong|incorrect|corrected|verified/i.test(out));
  for (const empty of [[], null, undefined]) assert.equal(renderToStaticMarkup(h(DataNotes, { notes: empty })), "");
});

test("only a warning-level note marks a product as worth checking", () => {
  assert.equal(hasWarning(NOTES), true);
  assert.equal(hasWarning([NOTES[1]]), false);
  assert.equal(hasWarning([]), false);
  assert.equal(hasWarning(null), false);
});

test("a confirmed line's detail shows its product's data notes, and an unconfirmed line shows none", () => {
  const props = { editable: false, onEdit() {}, onReviewGuess() {}, onMarkUnmatched() {}, onExplain() {} };
  const detail = JSON.parse(JSON.stringify(fixture.detail));
  const confirmed = buildDecisionRows(detail).find((r) => r.doctorMedicine);
  const target = (detail.detected_medicines || []).find((m) => m.pm_id === confirmed.id);
  target.data_notes = NOTES;
  const row = buildDecisionRows(detail).find((r) => r.id === confirmed.id);
  assert.deepEqual(row.dataNotes, NOTES);
  assert.ok(text(renderToStaticMarkup(h(Detail, { row, ...props }))).includes(NOTES[0].text));
  const unconfirmed = buildDecisionRows(detail).find((r) => !r.doctorMedicine);
  assert.deepEqual(unconfirmed.dataNotes, []);
  assert.ok(!text(renderToStaticMarkup(h(Detail, { row: { ...unconfirmed, dataNotes: NOTES }, ...props }))).includes(NOTES[0].text), "an unconfirmed line names no product, so no product notes");
});

// ---- Objectives 4 and 6: sources, freshness and outside services -----------------------------------------------------------------

const SOURCES = [
  { source_key: "indian_medicine_dataset", name: "Indian Medicine Dataset", kind: "reference_dataset", url: "https://example.invalid", license: "MIT", license_recorded: true, record_count: 253973, retrieved_at: "2026-08-28T10:00:00", notes: "Quality check.", demo: false, pharmacies: null, observations: null, latest_observed_at: null, latest_received_at: null },
  { source_key: "acme", name: "Acme Pharmacy feed", kind: "pharmacy_feed", url: null, license: null, license_recorded: false, record_count: 5, retrieved_at: "2026-10-18T10:05:00", notes: null, demo: false, pharmacies: 2, observations: 5, latest_observed_at: "2026-10-18T10:00:00", latest_received_at: "2026-10-18T10:05:00" },
  { source_key: "quiet", name: "Quiet feed", kind: "pharmacy_feed", url: null, license: null, license_recorded: false, record_count: 0, retrieved_at: null, notes: null, demo: false, pharmacies: 0, observations: 0, latest_observed_at: null, latest_received_at: null },
];
const SERVICES = [
  { key: "google_vision", name: "Google Cloud Vision (reading prescription text)", configured: true, when_unavailable: "The local EasyOCR reader is used instead. It is weaker on handwriting, so more lines will need verification." },
  { key: "gemini", name: "Google Gemini (plain-language summary and medicine explanation)", configured: false, when_unavailable: "A plain template summary is written from the same figures. Nothing is lost except the wording." },
];

test("the data sources show the live status, each feed's freshness, and say plainly when a feed has delivered nothing", () => {
  const out = text(renderToStaticMarkup(h(DataSourcesList, { sources: SOURCES, live: NO_FEED, services: SERVICES })));
  assert.ok(out.includes("No live feed connected"));
  assert.ok(out.includes("2,53,973 records"), "counts use Indian digit grouping");
  assert.ok(out.includes("licence: MIT"));
  assert.ok(out.includes("licence: not recorded"));
  assert.ok(out.includes("2 pharmacies, 5 reports"));
  assert.match(out, /newest report observed .*2026.* last data received .*2026/);
  assert.ok(out.includes("nothing has been reported by this feed yet"));
});

test("the reference dataset shows no pharmacy freshness line", () => {
  const out = text(renderToStaticMarkup(h(DataSourcesList, { sources: [SOURCES[0]] })));
  assert.ok(!out.includes("newest report observed") && !out.includes("nothing has been reported"));
  assert.ok(!out.includes("Outside services"), "no services were given, so no section");
});

test("outside services say whether each is configured, what happens without it, and that configured is not working", () => {
  const out = text(renderToStaticMarkup(h(ExternalServices, { services: SERVICES })));
  assert.ok(out.includes("Outside services"));
  assert.ok(out.includes("Google Cloud Vision (reading prescription text) Configured"));
  assert.ok(out.includes("Google Gemini (plain-language summary and medicine explanation) Not configured"));
  assert.ok(out.includes("If it is unavailable: The local EasyOCR reader is used instead."));
  assert.ok(out.includes("“Configured” means set up on this server, not that the service is working right now."));
  assert.equal(renderToStaticMarkup(h(ExternalServices, { services: null })), "");
  assert.equal(renderToStaticMarkup(h(ExternalServices, { services: [] })), "");
});
