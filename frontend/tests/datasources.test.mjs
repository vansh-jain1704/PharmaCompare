// The data-source list: each source with its size, date, licence AS RECORDED and quality note; nothing assumed.
//
//   npm run test:logic
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { DataSourcesList } from "../.test-build/entry.js";

const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
const render = (sources) => text(renderToStaticMarkup(React.createElement(DataSourcesList, { sources })));

// record counts use Indian digit grouping (2,53,973), the same on every machine
const medicines = {
  source_key: "indian_medicine_dataset", name: "Indian Medicine Dataset (junioralive, GitHub)", kind: "reference_dataset", url: "https://github.com/junioralive/Indian-Medicine-Dataset",
  license: "MIT (as stated by the source repository)", license_recorded: true, record_count: 253973, retrieved_at: "2026-08-28T12:14:39", demo: false,
  notes: "Quality check on 2026-10-18: 4 have no usable price.", pharmacies: null, observations: null,
};
const interactions = { ...medicines, source_key: "ddinter_2", name: "DDInter 2.0 drug-drug interactions", kind: "interaction_dataset", license: null, license_recorded: false, record_count: 160235, notes: "56.9% of salts are tracked." };

test("each source shows its name, kind, size, date, licence and quality note", () => {
  const out = render([medicines]);
  for (const needle of ["Indian Medicine Dataset", "Medicine reference data", "2,53,973 records", "2026", "licence: MIT (as stated by the source repository)", "4 have no usable price", "github.com/junioralive"]) {
    assert.ok(out.includes(needle), needle);
  }
});

test("a licence the repository does not record is shown as not recorded, never assumed", () => {
  const out = render([interactions]);
  assert.match(out, /licence: not recorded/);
  assert.match(out, /1,60,235 records/);
});

test("a pharmacy feed shows its counts and demo data is labelled", () => {
  const feed = { ...medicines, source_key: "feed", name: "Acme feed", kind: "pharmacy_feed", license: null, license_recorded: false, record_count: null, pharmacies: 3, observations: 120, notes: null, url: null, retrieved_at: null };
  const demo = { ...feed, source_key: "demo", name: "Demo feed", kind: "synthetic_demo", demo: true };
  const out = render([feed, demo]);
  assert.match(out, /3 pharmacies, 120 reports/);
  assert.match(out, /Pharmacy feed/);
  assert.match(out, /Demo data \(not real\)/);
  assert.match(out, /obtained not recorded/);
});

test("with nothing registered it says so", () => {
  assert.match(render([]), /No data sources are registered yet/);
});

test("the About page lists the data sources and does not claim a live stock source", () => {
  const page = readFileSync(new URL("../src/pages/About.jsx", import.meta.url), "utf8");
  assert.match(page, /<DataSources \/>/);
  assert.match(page, /There is no live stock source built in/);
  assert.doesNotMatch(page, /real-time (price|availability|stock)/i);
});
