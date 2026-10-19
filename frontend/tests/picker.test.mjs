// The manual verification flow: what the picker shows for each product, the suggestions listed when it opens, and
// the rule that nothing is confirmed by opening it or by choosing a row - only by the confirm button.
//
//   npm run test:logic
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MedicinePickerDialog } from "../.test-build/entry.js";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

const METFORMIN_SR = {
  medicine_id: 11, medicine_name: "Glyciphage SR 500 Tablet", composition: "Metformin (500mg)", strength: "500mg",
  form: "Tablet", manufacturer: "Franco-Indian", release_type: "sr", composition_incomplete: 0, is_discontinued: 0,
};
const PAN_D = {
  medicine_id: 12, medicine_name: "Pan-D Capsule PR", composition: "Pantoprazole (40mg) + Domperidone (30mg)", strength: "40mg + 30mg",
  form: "Capsule", manufacturer: "Alkem", release_type: "pr", composition_incomplete: 0, is_discontinued: 0,
};
const OLD = { medicine_id: 13, medicine_name: "Oldex Tablet", composition: "Alpha (5mg)", form: "Tablet", is_discontinued: 1, composition_incomplete: 1, release_type: null };

const render = (props) =>
  renderToStaticMarkup(React.createElement(MedicinePickerDialog, { open: true, onCancel() {}, onConfirm() {}, saving: false, ...props }));
// the small coloured labels on a product: release type, discontinued, ingredient list incomplete
const tags = (html) => [...html.matchAll(/<span class="tag tag-warning">([^<]*)<\/span>/g)].map((m) => m[1]);
const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

test("a closed dialog renders nothing", () => {
  assert.equal(render({ open: false, rawText: "x", suggestions: [PAN_D] }), "");
});

test("when Verify opens, the stored candidates are listed with name, ingredients, strength, form and release type", () => {
  const out = text(render({ rawText: "T. pan - D 100", suggestions: [METFORMIN_SR, PAN_D] }));
  assert.match(out, /Read from your prescription: .{1,3}T\. pan - D 100/);
  assert.match(out, /Suggested for this line/);
  for (const needle of ["Glyciphage SR 500 Tablet", "Contains: Metformin (500mg)", "500mg · Tablet · Franco-Indian", "Sustained release",
    "Pan-D Capsule PR", "Contains: Pantoprazole (40mg) + Domperidone (30mg)", "40mg + 30mg · Capsule · Alkem", "Prolonged release"]) {
    assert.ok(out.includes(needle), `missing: ${needle}`);
  }
});

test("the suggestions are labelled as not confirmed, and nothing is selected or confirmable on open", () => {
  const html = render({ rawText: "T. pan - D 100", suggestions: [PAN_D] });
  assert.match(text(html), /not confirmed/);
  assert.equal((html.match(/aria-pressed="true"/g) || []).length, 0);
  assert.match(html, /aria-pressed="false"/);
  // the confirm button is disabled until a row is chosen
  const confirm = html.match(/<button[^>]*>\s*Confirm medicine\s*<\/button>/)?.[0];
  assert.ok(confirm, "confirm button not found");
  assert.match(confirm, /disabled/);
});

test("with no stored candidates it just asks for a search - no suggestion section", () => {
  for (const suggestions of [[], undefined]) {
    const out = text(render({ rawText: "Shel cal soong", suggestions }));
    assert.doesNotMatch(out, /Suggested for this line/);
    assert.match(out, /Type at least 2 characters to search/);
  }
});

test("adding a medicine by hand has its own wording and the same disabled button", () => {
  const html = render({ rawText: "", suggestions: [] });
  assert.match(text(html), /Add a medicine/);
  assert.match(html.match(/<button[^>]*>\s*Add medicine\s*<\/button>/)?.[0] || "", /disabled/);
});

test("discontinued products and incomplete ingredient lists are tagged", () => {
  const out = text(render({ rawText: "x", suggestions: [OLD] }));
  assert.match(out, /Discontinued/);
  assert.match(out, /Ingredient list incomplete/);
  assert.equal(tags(render({ rawText: "x", suggestions: [OLD] })).filter((t) => /release/i.test(t)).length, 0);   // a plain product gets no release tag
  assert.ok(!text(render({ rawText: "x", suggestions: [{ ...OLD, is_discontinued: 0, composition_incomplete: 0 }] })).includes("Discontinued"));
});

test("a plain product shows no release tag, and an unknown release code still shows as modified release", () => {
  const clean = { ...OLD, is_discontinued: 0, composition_incomplete: 0 };
  assert.deepEqual(tags(render({ rawText: "x", suggestions: [clean] })), []);
  assert.deepEqual(tags(render({ rawText: "x", suggestions: [{ ...clean, release_type: "zz" }] })), ["Modified release"]);
  assert.deepEqual(tags(render({ rawText: "x", suggestions: [{ ...clean, release_type: "sr" }] })), ["Sustained release"]);
});

test("the backend's readable release label is used when it is sent", () => {
  const out = text(render({ rawText: "x", suggestions: [{ ...OLD, release_type: "sr", release_label: "sustained release", is_discontinued: 0, composition_incomplete: 0 }] }));
  assert.match(out, /Sustained release/);
});

test("a medicine is confirmed only by the confirm button (static guard)", () => {
  const source = read("../src/components/MedicinePickerDialog.jsx");
  assert.equal((source.match(/onConfirm\(/g) || []).length, 1, "onConfirm must be called from exactly one place");
  assert.match(source, /disabled=\{!selected \|\| saving\}\s*onClick=\{\(\) => onConfirm\(selected\)\}/);
  // choosing a row only selects it
  assert.match(source, /onClick=\{\(\) => onSelect\(medicine\)\}/);
});

test("the analysis table hands the picker the stored candidates for the line being verified", () => {
  const source = read("../src/components/results/MedicineTable.jsx");
  assert.match(source, /<MedicinePickerDialog[^]*?\ssuggestions=\{pickerSuggestions\}/);
  // what it is given: the several close matches, else the stored look-alikes
  assert.match(source, /pickerSuggestions\s*=[^;]*matchOptions[^;]*closestGuesses/);
});

test("the About page no longer describes simulated availability", () => {
  const source = read("../src/pages/About.jsx");
  assert.doesNotMatch(source, /simulated/i);
  assert.match(source, /appear only where a pharmacy has reported them/);
  assert.match(source, /no pharmacy has reported/);
});
