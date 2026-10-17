// Availability: PharmaCompare has no pharmacy stock data, so the screen must never show a stock reading.
// The only real status is the dataset's discontinued flag; everything else says "not tracked".
//
//   npm run test:logic
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AvailabilityDisclaimer, AvailabilityStatus } from "../.test-build/entry.js";

const NOT_TRACKED = "Availability is not tracked — confirm with your pharmacy";
const DISCONTINUED = "Discontinued by manufacturer";
// every wording the old simulated readings could produce, and the words that implied live stock
const FORBIDDEN = [/in stock/i, /limited stock/i, /hard to find/i, /nearby/i, /\bdemo\b/i, /simulated/i, /out of stock/i, /available now/i];

const render = (props) => renderToStaticMarkup(React.createElement(AvailabilityStatus, props));
const text = (html) => html.replace(/<[^>]+>/g, "").trim();

test("a medicine that is not discontinued says availability is not tracked - never a stock level", () => {
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
  assert.match(notice, /not tracked/i);
  assert.match(notice, /no pharmacy stock feed/i);
  assert.match(notice, /Discontinued by manufacturer/);
  assert.match(notice, /confirm with your pharmacy/i);
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
