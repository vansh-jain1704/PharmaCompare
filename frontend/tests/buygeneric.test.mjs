// Buy Generic: a web-search link built from verified active ingredients, strength and dosage form, and nothing else.
//
// What is checked: the URL (host, parameters, encoding), that it is built from ingredients and never from a brand, that anything uncertain gets
// a "verify first" request instead of a guessed search, that the control sits beside the medicine's name in the search results, the drawer and the
// prescription table, and that every external link is safe. What cannot be checked here: what the shopping site shows. Nothing in this feature
// claims a price, availability or stock, and these tests pin that down.
//
//   npm run test:logic
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  BUY_GENERIC_NOTE, BuyGenericButton, MAX_QUERY_CHARS, MedicineDrawer, MedicineResultCard, MedicineTable, MemoryRouter, SEARCH_BASE, VerifyFirstNote,
  buildDecisionRows, parseComposition, productBuyGeneric, rowBuyGeneric, rowStatus,
} from "../.test-build/entry.js";

const h = React.createElement;
const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
const analysis = JSON.parse(readFileSync(new URL("./fixtures/analysis.json", import.meta.url), "utf8"));
const handwritten = JSON.parse(readFileSync(new URL("./fixtures/handwritten.json", import.meta.url), "utf8"));

const dolo = { medicine_id: 1, medicine_name: "Dolo 650 Tablet", composition: "Paracetamol (650mg)", form: "Tablet", strength: "650mg", release_type: null, composition_incomplete: false, data_notes: [] };
const augmentin = { ...dolo, medicine_name: "Augmentin 625 Duo Tablet", composition: "Amoxycillin (500mg) + Clavulanic Acid (125mg)", strength: "500mg" };

// ---- ingredients -----------------------------------------------------------------------------------------------------------------

test("a composition is split into ingredients with their strengths", () => {
  assert.deepEqual(parseComposition("Paracetamol (650mg)"), [{ name: "Paracetamol", strength: "650mg" }]);
  assert.deepEqual(parseComposition("Amoxycillin (500mg) + Clavulanic Acid (125mg)"), [{ name: "Amoxycillin", strength: "500mg" }, { name: "Clavulanic Acid", strength: "125mg" }]);
  assert.deepEqual(parseComposition("Paracetamol (250mg/5ml)"), [{ name: "Paracetamol", strength: "250mg/5ml" }]);
  assert.deepEqual(parseComposition("  Lactobacillus  ( 60Million   spores ) "), [{ name: "Lactobacillus", strength: "60Million spores" }]);
});

test("an ingredient with no written strength has none, and a missing composition has no ingredients", () => {
  assert.deepEqual(parseComposition("Vitamin D3"), [{ name: "Vitamin D3", strength: null }]);
  assert.deepEqual(parseComposition("Foo (as directed)"), [{ name: "Foo", strength: null }]);
  for (const missing of [null, undefined, "", "  ", "NA", "n/a", "nan", "none", "-"]) assert.deepEqual(parseComposition(missing), [], String(missing));
});

// ---- the URL ---------------------------------------------------------------------------------------------------------------------

test("the search is for the ingredients, strength and form, as a Google Shopping query for India", () => {
  const v = productBuyGeneric(dolo);
  assert.equal(v.ok, true);
  assert.equal(v.query, "Paracetamol 650mg tablet");
  const url = new URL(v.url);
  assert.equal(`${url.origin}${url.pathname}`, SEARCH_BASE);
  assert.equal(url.searchParams.get("tbm"), "shop");
  assert.equal(url.searchParams.get("q"), "Paracetamol 650mg tablet");
  assert.equal(url.searchParams.get("gl"), "in");
  assert.equal(url.searchParams.get("hl"), "en");
  assert.deepEqual([...url.searchParams.keys()].sort(), ["gl", "hl", "q", "tbm"], "nothing else is sent");
});

test("every ingredient of a combination is in the search, each with its own strength", () => {
  assert.equal(productBuyGeneric(augmentin).query, "Amoxycillin 500mg and Clavulanic Acid 125mg tablet");
  assert.equal(productBuyGeneric({ ...dolo, composition: "Paracetamol (250mg/5ml)", form: "Syrup" }).query, "Paracetamol 250mg/5ml syrup");
});

test("the search never contains the brand name: it is for the generic, not for that product", () => {
  for (const m of [dolo, augmentin]) {
    const q = productBuyGeneric(m).query.toLowerCase();
    for (const word of m.medicine_name.toLowerCase().split(/\s+/)) {
      if (!["tablet", "duo", "650", "625"].includes(word)) assert.ok(!q.includes(word), `${word} is a brand word`);
    }
  }
  assert.ok(!productBuyGeneric(dolo).query.toLowerCase().includes("dolo"));
});

test("a modified-release product is searched as modified release, so it is not confused with the plain tablet", () => {
  assert.equal(productBuyGeneric({ ...dolo, composition: "Metformin (500mg)", release_type: "sr" }).query, "Metformin 500mg tablet sustained release");
  assert.equal(productBuyGeneric({ ...dolo, composition: "Metformin (500mg)", release_type: "xyz" }).query, "Metformin 500mg tablet modified release");
  assert.equal(productBuyGeneric({ ...dolo, composition: "Metformin (500mg)", release_label: "extended release" }).query, "Metformin 500mg tablet extended release");
  assert.equal(productBuyGeneric({ ...dolo, composition: "Metformin (500mg)" }).query, "Metformin 500mg tablet");
});

test("odd characters are cleaned and encoded; they cannot add parameters or markup to the address", () => {
  const nasty = { ...dolo, composition: "Foo&tbm=evil\n\t<script>alert(1)</script> (5mg)", form: "Tab\u0000let" };
  const v = productBuyGeneric(nasty);
  assert.equal(v.ok, true);
  const url = new URL(v.url);
  assert.deepEqual([...url.searchParams.keys()].sort(), ["gl", "hl", "q", "tbm"]);
  assert.equal(url.searchParams.get("tbm"), "shop", "an ampersand in the data cannot override a parameter");
  // the control-character ranges are the point of these two checks
  // eslint-disable-next-line no-control-regex
  assert.ok(!/[\u0000-\u001f<>]/.test(v.url), "no control character or angle bracket reaches the address unencoded");
  // eslint-disable-next-line no-control-regex
  assert.ok(!/[\u0000-\u001f]/.test(url.searchParams.get("q")));
});

test("the host is fixed: nothing in the medicine's data can change where the link goes", () => {
  const hostile = [
    dolo, augmentin,
    { ...dolo, medicine_name: "https://evil.example", composition: "Foo (5mg)" },
    { ...dolo, composition: "https://evil.example/ @x (5mg)" },
    { ...dolo, composition: "Foo (5mg)", form: "//evil.example" },
  ];
  for (const m of hostile) {
    const v = productBuyGeneric(m);
    assert.equal(v.ok, true, JSON.stringify(m).slice(0, 80));
    assert.equal(new URL(v.url).origin, "https://www.google.com");
    assert.equal(new URL(v.url).pathname, "/search");
  }
});

// ---- uncertain medicines ---------------------------------------------------------------------------------------------------------

test("anything uncertain gets a reason and no link, query or guess", () => {
  const cases = [
    [null, /no medicine/i],
    [{ ...dolo, composition: null }, /No ingredient information/],
    [{ ...dolo, composition: "NA" }, /No ingredient information/],
    [{ ...dolo, composition: "" }, /No ingredient information/],
    [{ ...dolo, composition_incomplete: true }, /incomplete in the dataset/],
    [{ ...dolo, composition: "Paracetamol" }, /strength is missing/],
    [{ ...dolo, composition: "Paracetamol (650mg) + Caffeine" }, /strength is missing/],
    [{ ...dolo, form: null }, /dosage form is not on file/],
    [{ ...dolo, form: "NA" }, /dosage form is not on file/],
    [{ ...dolo, composition: Array.from({ length: 12 }, (_, i) => `Ingredient${i}longname (${i + 1}mg)`).join(" + ") }, /too many ingredients/],
  ];
  for (const [medicine, reason] of cases) {
    const v = productBuyGeneric(medicine);
    assert.equal(v.ok, false, JSON.stringify(medicine)?.slice(0, 60));
    assert.match(v.reason, reason);
    assert.deepEqual(Object.keys(v).sort(), ["ok", "reason"], "no url, no query: nothing is guessed");
  }
  assert.ok(MAX_QUERY_CHARS >= 100);
});

test("the server's data notes that make the ingredients unreliable also stop the search", () => {
  const note = (code) => [{ code, level: "warn", text: "x" }];
  assert.match(productBuyGeneric(dolo, note("ingredient_list_incomplete")).reason, /incomplete/);
  assert.match(productBuyGeneric(dolo, note("no_composition")).reason, /No ingredient information/);
  assert.match(productBuyGeneric(dolo, note("strength_not_in_composition")).reason, /could not be matched/);
  assert.match(productBuyGeneric(dolo, note("no_form")).reason, /dosage form/);
  for (const harmless of ["no_strength", "no_pack_size", "no_usable_price"]) assert.equal(productBuyGeneric(dolo, note(harmless)).ok, true, harmless);
  assert.equal(productBuyGeneric({ ...dolo, data_notes: note("strength_not_in_composition") }).ok, false, "a product's own notes are read when none are passed");
});

test("on the prescription, a line that is only suggested, unidentified, typed in or unsettled is never searched", () => {
  const rows = buildDecisionRows(handwritten);
  assert.equal(rows.length, 5);
  for (const row of rows) {
    const v = rowBuyGeneric(row);
    assert.equal(v.ok, false, row.rawText);
    assert.ok(v.reason.length > 20, row.rawText);
  }
  const pan = rows.find((r) => r.rawText.includes("pan"));
  assert.match(rowBuyGeneric(pan).reason, /only suggested \(Pan-D Capsule PR\), not confirmed/);
  assert.match(rowBuyGeneric(rows.find((r) => r.rawText.includes("Lincont"))).reason, /not been identified yet/);
  assert.match(rowBuyGeneric({ ...pan, suggested: false, userEntered: { name: "Zinconit" } }).reason, /entered this medicine yourself/);
  assert.match(rowBuyGeneric({ ...pan, suggested: false, userUnmatched: true }).reason, /marked this line as not identified/);
});

test("a matched line is searched only while nothing about the match is unsettled", () => {
  const rows = buildDecisionRows(analysis.detail);
  const settled = rows.filter((r) => r.doctorMedicine && !["Check match"].includes(rowStatus(r).text));
  const searchable = rows.filter((r) => rowBuyGeneric(r).ok);
  assert.ok(searchable.length > 0, "the fixture has matched lines");
  for (const row of rows) {
    const status = rowStatus(row).text;
    if (["Check match", "Needs verification", "Suggested", "Entered by you", "Not identified (by you)"].includes(status)) {
      assert.equal(rowBuyGeneric(row).ok, false, `${row.rawText} is ${status}`);
    }
    if (rowBuyGeneric(row).ok) assert.ok(["Matched", "Confirmed"].includes(status), `${row.rawText}: ${status}`);
  }
  assert.ok(settled.length >= searchable.length);
  const one = searchable[0];
  const q = rowBuyGeneric(one).query.toLowerCase();
  assert.ok(q.includes(one.doctorMedicine.composition.split(" (")[0].toLowerCase()), "the search names the line's ingredient");
  const base = searchable[0];
  for (const flag of ["needsDisambiguation", "ocrUncertain", "needsCheck", "confirmedWithConflicts"]) {
    assert.equal(rowBuyGeneric({ ...base, [flag]: true }).ok, false, flag);
  }
  assert.equal(rowBuyGeneric({ ...base, dataNotes: [{ code: "ingredient_list_incomplete", level: "warn", text: "x" }] }).ok, false);
});

// ---- the control -----------------------------------------------------------------------------------------------------------------

test("with a settled medicine the control is a link that opens in a new tab with no opener and no referrer", () => {
  const html = renderToStaticMarkup(h(BuyGenericButton, { verdict: productBuyGeneric(dolo) }));
  assert.match(html, /^<a /);
  assert.ok(html.includes(`href="${productBuyGeneric(dolo).url.replace(/&/g, "&amp;")}"`));
  assert.ok(html.includes('target="_blank"'));
  assert.match(html, /rel="noopener noreferrer"/);
  assert.ok(text(html).includes("Buy Generic"));
  assert.ok(html.includes("search Google Shopping for Paracetamol 650mg tablet (opens in a new tab)"));
  assert.ok(!html.includes("<button"));
});

test("with an uncertain medicine the control is a button, not a link, and asks for verification when pressed", () => {
  const verdict = productBuyGeneric({ ...dolo, composition_incomplete: true });
  const html = renderToStaticMarkup(h(BuyGenericButton, { verdict }));
  assert.match(html, /^<span /);
  assert.ok(html.includes("<button"));
  assert.ok(!html.includes("href="), "no address is built for an uncertain medicine");
  assert.ok(html.includes('aria-expanded="false"'));
  assert.ok(text(html).includes("Buy Generic"));
  assert.ok(!html.includes("Verify this medicine first"), "the note appears when it is pressed");
  const note = text(renderToStaticMarkup(h(VerifyFirstNote, { reason: verdict.reason, onVerify() {} })));
  assert.ok(note.includes("Verify this medicine first."));
  assert.ok(note.includes(verdict.reason));
  assert.ok(note.includes("We will not guess which product to search for."));
  assert.ok(note.includes("Verify now"));
  assert.ok(!text(renderToStaticMarkup(h(VerifyFirstNote, { reason: "x" }))).includes("Verify now"), "no verify step to open, so no button for it");
});

test("the control makes no claim about price, availability or stock", () => {
  const claims = /in stock|available|cheapest|best price|lowest|discount|offer|₹|live price|deliver/i;
  const ok = renderToStaticMarkup(h(BuyGenericButton, { verdict: productBuyGeneric(dolo) }));
  const unverified = renderToStaticMarkup(h(BuyGenericButton, { verdict: productBuyGeneric(null) }));
  const note = text(renderToStaticMarkup(h(VerifyFirstNote, { reason: "No ingredient information is on file for this product." })));
  for (const piece of [ok.replace("PharmaCompare shows no price or stock for it", ""), unverified, note]) assert.doesNotMatch(piece, claims);
  assert.match(BUY_GENERIC_NOTE, /shows no price, availability or stock for them/);
  assert.match(BUY_GENERIC_NOTE, /may include different brands: check the ingredients, strength and form of each product/);
  assert.match(BUY_GENERIC_NOTE, /new tab/);
  assert.doesNotMatch(BUY_GENERIC_NOTE.replace("shows no price, availability or stock for them", ""), claims);
});

// ---- where it appears ------------------------------------------------------------------------------------------------------------

test("each search result has the control beside its name, outside the card's button, and the card still opens the details", () => {
  const product = { ...dolo, manufacturer: "Micro Labs", price: 34.27, is_discontinued: false };
  const html = renderToStaticMarkup(h(MedicineResultCard, { medicine: product, index: 0, onOpen() {} }));
  assert.ok(html.includes("Open details for Dolo 650 Tablet"));
  assert.ok(text(html).includes("Dolo 650 Tablet") && text(html).includes("Buy Generic"));
  const [card, rest] = html.split("</button>");
  assert.ok(!card.includes("<a "), "no link inside the card's button");
  assert.ok(rest.includes('<a class="buy-generic"') && rest.includes('target="_blank"') && /rel="noopener noreferrer"/.test(rest));
  assert.ok(html.includes("Compare →"));
});

test("a search result whose ingredients are uncertain shows the verify-first control instead", () => {
  const html = renderToStaticMarkup(h(MedicineResultCard, { medicine: { ...dolo, composition: "Foo (5mg)", composition_incomplete: true, manufacturer: "x", price: 1 }, index: 1, onOpen() {} }));
  assert.ok(!html.includes("href="), "no link of any kind");
  assert.ok(html.includes('class="buy-generic is-unverified"'));
});

test("the medicine drawer has the control beside the name, and explains what it does and does not know", () => {
  const html = renderToStaticMarkup(h(MemoryRouter, null, h(MedicineDrawer, { medicine: { ...dolo, manufacturer: "x", price: 34.27, pack_size: "strip", is_discontinued: false }, results: [], query: "Dolo", onClose() {}, onExplain() {} })));
  assert.match(html, /<h2>Dolo 650 Tablet<a class="buy-generic"/);
  assert.ok(text(html).includes(BUY_GENERIC_NOTE));
});

function links(html) {
  return [...html.matchAll(/<a [^>]*href="(https?:[^"]+)"[^>]*>/g)].map((m) => ({ tag: m[0], href: m[1].replace(/&amp;/g, "&") }));
}
const tableHtml = (detail) => renderToStaticMarkup(h(MemoryRouter, null, h(MedicineTable, { detail })));

test("the prescription table has the control beside every medicine name, a link only for settled lines", () => {
  const rows = buildDecisionRows(analysis.detail);
  const html = tableHtml(analysis.detail);
  const searchable = rows.filter((r) => rowBuyGeneric(r).ok).length;
  const external = links(html);
  assert.equal(external.length, searchable);
  assert.equal((html.match(/class="buy-generic(?: is-unverified)?"/g) || []).length, rows.length, "one control per line");
  assert.equal((html.match(/class="buy-generic is-unverified"/g) || []).length, rows.length - searchable);
  for (const { href } of external) assert.ok(href.startsWith("https://www.google.com/search?tbm=shop&q="), href);
});

test("a prescription with no settled line has no external link at all", () => {
  const html = tableHtml(handwritten);
  assert.deepEqual(links(html), []);
  assert.equal((html.match(/class="buy-generic is-unverified"/g) || []).length, 5);
  assert.ok(!html.includes("google.com"));
});

test("every external link in the table is safe", () => {
  for (const detail of [analysis.detail, handwritten]) {
    for (const { tag } of links(tableHtml(detail))) {
      assert.ok(tag.includes('target="_blank"'));
      assert.match(tag, /rel="noopener noreferrer"/);
      assert.ok(!/javascript:|data:/i.test(tag));
    }
  }
});

// ---- found by running the whole real catalogue through the rule ------------------------------------------------------------------

test("a name that carries its own bracket stays whole: the strength is the last bracket", () => {
  assert.deepEqual(parseComposition("Progesterone (Natural Micronized) (25mg)"), [{ name: "Progesterone (Natural Micronized)", strength: "25mg" }]);
  assert.deepEqual(parseComposition("Polyvinyl Alcohol (Including Pvp) (1.4% w/v) + Povidone Iodine (0.6% w/v)"), [
    { name: "Polyvinyl Alcohol (Including Pvp)", strength: "1.4% w/v" }, { name: "Povidone Iodine", strength: "0.6% w/v" },
  ]);
  assert.deepEqual(parseComposition("Doxorubicin (Plain) (50mg)"), [{ name: "Doxorubicin (Plain)", strength: "50mg" }]);
});

test("a nested-bracket composition gives a well-formed search, never a half bracket", () => {
  const eyeDrop = { ...dolo, composition: "Polyvinyl Alcohol (Including Pvp) (1.4% w/v) + Povidone Iodine (0.6% w/v)", form: "Eye Drop" };
  assert.equal(productBuyGeneric(eyeDrop).query, "Polyvinyl Alcohol (Including Pvp) 1.4% w/v and Povidone Iodine 0.6% w/v eye drop");
  for (const composition of ["Progesterone (Natural Micronized) (25mg)", "Doxorubicin (Plain) (50mg)", "Standard Cobra Venom (Naja naja) (0.6mg) + Standard common krait Venom (Bangarus caeruleus) (0.45mg)"]) {
    const v = productBuyGeneric({ ...dolo, composition });
    assert.equal(v.ok, true, composition);
    const opens = (v.query.match(/\(/g) || []).length;
    const closes = (v.query.match(/\)/g) || []).length;
    assert.equal(opens, closes, `unbalanced brackets in: ${v.query}`);
    assert.ok(!/[)]\s*\(/.test(v.query), `a strength bracket was left inside the query: ${v.query}`);
  }
});

test("an ingredient that is really a drug class is refused, not searched", () => {
  for (const composition of [
    "Trimethoprim Combinations (50mg)", "Oxytocics And Prostaglandin E1 E2 And Products For Cervical Dilatation (5mg)",
    "Gonadotrophins Including Other Ovulation Stimulants (50mg)", "Gynaecological Products (5mg)", "Paracetamol (500mg) + Some Products (5mg)",
  ]) {
    const v = productBuyGeneric({ ...dolo, composition });
    assert.equal(v.ok, false, composition);
    assert.match(v.reason, /looks like a drug class, not a specific ingredient/);
    assert.deepEqual(Object.keys(v).sort(), ["ok", "reason"]);
  }
  for (const composition of ["Polyvinyl Alcohol (Including Pvp) (1.4% w/v)", "Meningococcal Vaccine (Group A, C, Y & W-135) (50mcg)", "Paracetamol (500mg)"]) {
    assert.equal(productBuyGeneric({ ...dolo, composition }).ok, true, composition);
  }
});

