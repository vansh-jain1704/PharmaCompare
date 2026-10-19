// Availability: the screen shows a stock status ONLY when a pharmacy has reported one (with its age and source).
// Without a report there is nothing to show, and it says so. The other real status is the dataset's discontinued flag.
//
//   npm run test:logic
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AvailabilityDisclaimer, AvailabilityStatus } from "../.test-build/entry.js";

const NOT_TRACKED = "No pharmacy stock report — confirm with your pharmacy";   // the wording when nothing has been reported
const DISCONTINUED = "Discontinued by manufacturer";
// every wording the old simulated readings could produce, and the words that implied live stock
const FORBIDDEN = [/in stock/i, /limited stock/i, /hard to find/i, /nearby/i, /\bdemo\b/i, /simulated/i, /out of stock/i, /available now/i];

const render = (props) => renderToStaticMarkup(React.createElement(AvailabilityStatus, props));
const text = (html) => html.replace(/<[^>]+>/g, "").trim();

test("a medicine with no pharmacy report says so - never a stock level", () => {
  for (let id = 0; id < 200; id += 1) {
    for (const compact of [true, false]) {
      const out = text(render({ medicine: { medicine_id: id }, discontinued: false, compact }));
      assert.equal(out, NOT_TRACKED, `id ${id} compact=${compact}`);
    }
  }
});

test("the reading no longer depends on the medicine id (the old simulation used id % 4)", () => {
  const readings = new Set();
  for (let id = 0; id < 40; id += 1) readings.add(render({ medicine: { medicine_id: id }, discontinued: false, compact: true }));
  assert.equal(readings.size, 1, "different medicine ids produced different readings");
  // and the same wording when no medicine is passed at all
  assert.equal(text(render({ discontinued: false })), NOT_TRACKED);
  assert.equal(text(render({})), NOT_TRACKED);
});

test("no simulated or live-stock wording is ever rendered", () => {
  for (let id = 0; id < 200; id += 1) {
    for (const discontinued of [false, true, undefined]) {
      const html = render({ medicine: { medicine_id: id }, discontinued, compact: id % 2 === 0 });
      for (const word of FORBIDDEN) assert.doesNotMatch(text(html), word, `id ${id} discontinued=${discontinued}`);
    }
  }
  for (const word of FORBIDDEN) assert.doesNotMatch(text(renderToStaticMarkup(React.createElement(AvailabilityDisclaimer))), word);
});

test("a product the dataset marks discontinued says so", () => {
  for (const flag of [true, 1]) {
    assert.equal(text(render({ medicine: { medicine_id: 7 }, discontinued: flag, compact: true })), DISCONTINUED);
  }
  assert.match(render({ discontinued: true }), /avail-out/);   // keeps its existing warning styling
});

test("only a true discontinued flag changes the wording", () => {
  for (const flag of [false, 0, null, undefined, ""]) assert.equal(text(render({ discontinued: flag })), NOT_TRACKED, String(flag));
});

test("the page-level notice states the limit and does not call anything simulated or planned", () => {
  const notice = text(renderToStaticMarkup(React.createElement(AvailabilityDisclaimer)));
  assert.match(notice, /only where a pharmacy has reported it/i);
  assert.match(notice, /no pharmacy has reported/i);
  assert.match(notice, /Discontinued by manufacturer/);
  assert.match(notice, /check with your pharmacy/i);
  assert.match(notice, /may be out of date/i);
});

test("no frontend source file can render the old simulated readings", () => {
  const walk = (dir) => readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
  const offenders = [];
  for (const file of walk(new URL("../src", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"))) {
    if (!/\.(jsx?|mjs)$/.test(file)) continue;
    const source = readFileSync(file, "utf8");
    if (/In stock nearby|Limited stock|Hard to find|SIMULATED_STATES|simulatedFor|medicine_id\)\s*\|\|\s*0|seed % /.test(source)) offenders.push(file);
  }
  assert.deepEqual(offenders, []);
});

// ---- when a pharmacy HAS reported ----------------------------------------------------------------------------------------
const reported = (status, label, extra = {}) => ({ count: 1, has_demo_data: false, availability: { status, label }, items: [], ...extra });

test("a fresh pharmacy report is shown exactly as the backend worded it, with its tone", () => {
  const cases = [
    ["in_stock", "In stock at 2 of 2 pharmacy reports, latest report 2 hours ago", /avail-in/],
    ["limited", "Limited stock at 1 of 1 pharmacy report, latest report 1 hour ago", /avail-low/],
    ["mixed", "In stock at 1, out of stock at 1 (2 pharmacy reports), latest report 3 hours ago", /avail-low/],
    ["out_of_stock", "Out of stock at all 2 reporting pharmacies, latest report 1 hour ago", /avail-out/],
    ["stale", "Last reported 4 days ago (in stock at A): may have changed", /avail-unknown/],
  ];
  for (const [status, label, tone] of cases) {
    const html = render({ discontinued: false, offers: reported(status, label) });
    assert.equal(text(html), label, status);
    assert.match(html, tone, status);
  }
});

test("a stale report is worded as possibly out of date and never as a current stock level", () => {
  const out = text(render({ offers: reported("stale", "Last reported 4 days ago (in stock at A): may have changed") }));
  assert.match(out, /may have changed/);
  assert.match(out, /Last reported 4 days ago/);
});

test("no report for the medicine, or an empty offers object, says no report exists", () => {
  for (const offers of [null, undefined, { count: 0, items: [], availability: { status: "not_reported", label: "No pharmacy has reported stock for this medicine" } }]) {
    assert.equal(text(render({ offers })), NOT_TRACKED);
  }
});

test("demo data is always labelled", () => {
  const html = render({ offers: reported("in_stock", "In stock at 1 of 1 pharmacy report, latest report 1 hour ago", { has_demo_data: true }) });
  assert.match(text(html), /Demo data/);
  assert.doesNotMatch(text(render({ offers: reported("in_stock", "In stock at 1 of 1 pharmacy report, latest report 1 hour ago") })), /Demo data/);
});

test("discontinued still outranks any stock report", () => {
  const out = text(render({ discontinued: true, offers: reported("in_stock", "In stock at 3 of 3 pharmacy reports, latest report 1 hour ago") }));
  assert.equal(out, DISCONTINUED);
});
