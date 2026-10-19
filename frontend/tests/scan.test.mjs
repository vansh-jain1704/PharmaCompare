// Scanning a medicine pack: candidates for the text read, never a confirmation.
//
//   npm run test:logic
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ScanResults } from "../.test-build/entry.js";

const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
const render = (result) => text(renderToStaticMarkup(React.createElement(ScanResults, { result, onOpen() {} })));
const NOTICE = "These are possible matches for the text read from the pack. They are not a confirmation: check the name, strength and maker printed on your pack against each one. A scan cannot tell whether a pack is genuine.";

const candidate = (over = {}) => ({
  medicine_id: 1, medicine_name: "Dolo 650 Tablet", composition: "Paracetamol (650mg)", strength: "650mg", display_strength: "650mg", form: "Tablet", release_label: null,
  manufacturer: "Micro Labs Ltd", price: 34.27, is_discontinued: false, settled_by_reader: true, from_line: "DOLO 650", reasons: [], ...over,
});

test("the notice comes first and says a scan is not a confirmation", () => {
  const out = render({ notice: NOTICE, candidates: [candidate()], lines: [], image_quality: null });
  assert.ok(out.indexOf("not a confirmation") < out.indexOf("Dolo 650 Tablet"));
  assert.match(out, /cannot tell whether a pack is genuine/);
});

test("each candidate shows its name, ingredients, strength, form, maker, price and the line it came from", () => {
  const out = render({ notice: NOTICE, candidates: [candidate()], lines: [], image_quality: null });
  for (const needle of ["Dolo 650 Tablet", "Paracetamol (650mg)", "650mg · Tablet", "Micro Labs Ltd", "34.27", "Offered because of the line: “DOLO 650”"]) assert.ok(out.includes(needle), needle);
});

test("the best match is labelled as not confirmed, and no candidate is ever called confirmed or verified", () => {
  const out = render({ notice: NOTICE, candidates: [candidate(), candidate({ medicine_id: 2, medicine_name: "Other 650", settled_by_reader: false, reasons: ["The name as read is only similar to this product."] })], lines: [], image_quality: null });
  assert.match(out, /Best match for the text \(not confirmed\)/);
  assert.equal((out.match(/Best match for the text/g) || []).length, 1);
  assert.match(out, /The name as read is only similar to this product/);
  assert.doesNotMatch(out, /Confirmed|Verified|Authentic/);   // the notice says "not a confirmation" (lower case); nothing is ever called confirmed
});

test("a combination product shows every ingredient's strength", () => {
  const out = render({ notice: NOTICE, lines: [], image_quality: null, candidates: [candidate({ medicine_name: "Pan-D Capsule PR", strength: "30mg", display_strength: "Domperidone 30mg + Pantoprazole 40mg", form: "Capsule", release_label: "prolonged release" })] });
  assert.match(out, /Domperidone 30mg \+ Pantoprazole 40mg · Capsule · prolonged release/);
});

test("with no candidates it says nothing matched instead of guessing", () => {
  const out = render({ notice: NOTICE, candidates: [], message: "Nothing on file matches the text read from this pack. Try the medicine search, or a clearer photo of the front of the pack.", lines: [{ text: "xqzvbw" }], image_quality: null });
  assert.match(out, /Nothing on file matches the text read from this pack/);
  assert.match(out, /Text read from the pack/);
  assert.match(out, /xqzvbw/);
});

test("photo notes appear with the results", () => {
  const out = render({ notice: NOTICE, candidates: [], message: "x", lines: [], image_quality: { warnings: [{ code: "blurry", text: "The photo looks blurry or out of focus." }], checked: ["sharpness"] } });
  assert.match(out, /About the photo/);
  assert.match(out, /blurry or out of focus/);
});

test("the page sends the photo once, from the button, and is reachable from the navigation", () => {
  const page = readFileSync(new URL("../src/pages/ScanMedicine.jsx", import.meta.url), "utf8");
  assert.equal((page.match(/scanMedicine\(file\)/g) || []).length, 1);
  assert.match(page, /The photo is read once and not kept/);
  assert.match(readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8"), /path="\/scan" element=\{guarded\(<ScanMedicine \/>\)\}/);
  assert.match(readFileSync(new URL("../src/components/SiteHeader.jsx", import.meta.url), "utf8"), /to: "\/scan", label: "Scan"/);
});
