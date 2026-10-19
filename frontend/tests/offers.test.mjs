// What pharmacies have reported (price, stock, age, source): shown as reported, never mixed with the dataset's reference price,
// and honest when nothing has been reported.
//
//   npm run test:logic
import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Detail, PharmacyOffers, buildDecisionRows } from "../.test-build/entry.js";

const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
const render = (offers) => text(renderToStaticMarkup(React.createElement(PharmacyOffers, { offers })));

const item = (over = {}) => ({
  pharmacy: "Demo Pharmacy A", city: "Demo City", price: 30.5, price_stale: false, availability: "in_stock", availability_label: "In stock",
  stock_stale: false, quantity_available: 20, observed_at: "2026-10-18T10:00:00", age: "2 hours ago", source: "Test feed", source_kind: "pharmacy_feed", demo: false, ...over,
});
const offers = (items, over = {}) => ({ items, count: items.length, has_demo_data: false, availability: { status: "in_stock", label: "In stock" }, cheapest: items[0] || null, ...over });

test("with no reports it says so, and does not present the dataset price as a pharmacy price", () => {
  for (const value of [null, undefined, offers([])]) {
    const out = render(value);
    assert.match(out, /No pharmacy has reported a price or stock for this medicine/);
    assert.match(out, /reference price comes from a dataset snapshot, not from a pharmacy/);
  }
});

test("each report shows the pharmacy, city, age, source, stock and price", () => {
  const out = render(offers([item()]));
  for (const needle of ["Demo Pharmacy A", "Demo City", "reported 2 hours ago", "Test feed", "In stock", "20 reported", "30.50"]) assert.ok(out.includes(needle), needle);
  assert.match(out, /not checked by PharmaCompare/);
  assert.match(out, /confirm with the pharmacy/);
});

test("old stock and old prices are labelled as old", () => {
  const out = render(offers([item({ stock_stale: true, price_stale: true, age: "6 days ago" })]));
  assert.match(out, /old report: may have changed/);
  assert.match(out, /old price/);
});

test("a report with no price says 'No price', and one with no stock says the stock is not stated", () => {
  const out = render(offers([item({ price: null }), item({ pharmacy: "B", availability: "unknown", availability_label: "Stock not stated", quantity_available: null })]));
  assert.match(out, /No price/);
  assert.match(out, /Stock not stated/);
});

test("demo data is announced before anything else", () => {
  const out = render(offers([item({ demo: true, source: "Demo feed" })], { has_demo_data: true }));
  assert.match(out, /Demo data\. These are not real pharmacies and not real prices/);
  assert.match(out, /Demo feed \(demo\)/);
  assert.ok(out.indexOf("Demo data") < out.indexOf("Demo Pharmacy A"));
  assert.doesNotMatch(render(offers([item()])), /Demo data/);
});

test("a long list says how many are shown", () => {
  const out = render(offers([item()], { count: 12 }));
  assert.match(out, /Showing 1 of 12 pharmacies/);
});

test("an identified line's detail has an 'At pharmacies' block, and an unidentified line's has none", () => {
  const base = { pm_id: 1, raw_text: "Tab Dolo 650", match_confidence: "1", closest_guesses: [], verification_reasons: [] };
  const matched = { ...base, match_status: "matched", medicine_id: 5, medicine_name: "Dolo 650 Tablet", composition: "Paracetamol (650mg)", form: "Tablet", strength: "650mg", price: "34.27" };
  const show = (line) => text(renderToStaticMarkup(React.createElement(Detail, {
    row: buildDecisionRows({ detected_medicines: [line], price_comparison: [], recommendations: [], clinical_analysis: { findings: [] } })[0], editable: false, saving: false, busy: false,
  })));
  const withOffers = show({ ...matched, offers: offers([item()], { availability: { status: "in_stock", label: "In stock at 1 of 1 pharmacy report, latest report 2 hours ago" } }) });
  assert.match(withOffers, /At pharmacies \(as reported\)/);
  assert.match(withOffers, /Demo Pharmacy A/);
  assert.match(withOffers, /Availability In stock at 1 of 1 pharmacy report/);
  const none = show({ ...matched, offers: null });
  assert.match(none, /No pharmacy has reported a price or stock/);
  assert.match(none, /Availability No pharmacy stock report/);
  assert.doesNotMatch(show({ ...base, match_status: "needs_verification", medicine_id: null, offers: null }), /At pharmacies/);
});
