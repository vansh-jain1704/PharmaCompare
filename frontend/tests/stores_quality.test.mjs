// The Stores page's listing quality on screen: names, addresses, old listings, merged duplicates, distinct markers that match the list, and the
// category filters. The stores are made-up test inputs; the wording they are checked against is what the page says for real entries.
//
//   npm run test:logic
import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  MARKER_KINDS, SCOPE_OPTIONS, StoreCard, StoreMap, StoreMapKey, StoreResults, addressLine, editedNote, keyEntries, markerKind, scopeNoun,
} from "../.test-build/entry.js";

const h = React.createElement;
const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

const base = (over = {}) => ({
  store_id: "osm:node/1", name: "Manjula Medicals", name_listed: true, category: "pharmacy", category_label: "Pharmacy",
  address: "Hadadi Road, Davanagere, 577002", address_level: "full", address_parts: { street: "Hadadi Road", locality: null, town: "Davanagere", postcode: "577002" },
  lat: 14.465, lon: 75.922, distance_m: 810, distance_text: "810 m", phone: null, phone_link: null, website: null, opening_hours: null,
  directions_url: "https://www.google.com/maps/dir/?api=1&destination=14.465000,75.922000", source: "OpenStreetMap", listing_last_edited: "2026-03-14",
  listing_old: false, also_listed_as: [], verified: false, ...over,
});
const result = (stores, over = {}) => ({
  center: { lat: 14.464, lon: 75.922 }, radius_km: 5, scope: "all", count: stores.length, stores, may_be_incomplete: false, duplicates_merged: 0,
  attribution: "Store data © OpenStreetMap contributors (ODbL). Map tiles © OpenStreetMap contributors.",
  verification_note: "These stores come from OpenStreetMap, a map edited by volunteers. PharmaCompare has not verified them: a listing can be incomplete, out of date or missing, and a store may have moved or closed.",
  official_locator_url: "https://janaushadhi.gov.in/locate-kendra", location_note: "Your position was rounded to about 100 m for this search and is not stored.", ...over,
});
const card = (store) => renderToStaticMarkup(h(StoreCard, { store, number: 1, selected: false, onSelect() {} }));
const results = (stores, over = {}, props = {}) => renderToStaticMarkup(h(StoreResults, { result: result(stores, over), selectedRef: null, onSelect() {}, ...props }));

const mixed = [
  base({ store_id: "osm:node/1", name: "Manjula Medicals", distance_m: 100 }),
  base({ store_id: "osm:node/2", name: "Pradhana Mantri Jan Aushadi Kendra", category: "jan_aushadhi", category_label: "Jan Aushadhi Kendra", lat: 14.466, distance_m: 200 }),
  base({ store_id: "osm:node/3", name: "Pharmacy — name unavailable", name_listed: false, address: null, address_level: "none", lat: 14.467, distance_m: 300 }),
  base({ store_id: "osm:way/4", name: "Cure Generic Medicals", category: "generic", category_label: "Generic medicine store", lat: 14.468, distance_m: 400 }),
  base({ store_id: "osm:node/5", name: "Another Chemist", lat: 14.469, distance_m: 500 }),
];

// ---- names -----------------------------------------------------------------------------------------------------------------------

test("a store with no name says so in the stated words and is marked as unnamed, with no invented name", () => {
  const html = card(base({ name: "Pharmacy — name unavailable", name_listed: false }));
  assert.ok(text(html).includes("Pharmacy — name unavailable"));
  assert.match(html, /<strong class="is-unnamed">Pharmacy — name unavailable<\/strong>/);
  assert.ok(!text(html).includes("Medicals"));
});

test("a store with a listed name shows it as listed and not as unnamed", () => {
  const html = card(base());
  assert.match(html, /<strong>Manjula Medicals<\/strong>/);
  assert.ok(!html.includes("is-unnamed"));
});

// ---- addresses -------------------------------------------------------------------------------------------------------------------

test("a full address is shown as listed, a partial one says it is partial, and none says it is not listed", () => {
  assert.deepEqual(addressLine(base()), { text: "Hadadi Road, Davanagere, 577002", note: null });
  assert.deepEqual(addressLine(base({ address: "Davanagere, 577004", address_level: "partial" })), { text: "Davanagere, 577004", note: "partial address" });
  assert.deepEqual(addressLine(base({ address: null, address_level: "none" })), { text: null, note: null });
  const full = text(card(base()));
  assert.ok(full.includes("Hadadi Road, Davanagere, 577002") && !full.includes("partial address") && !full.includes("Address not listed"));
  const partial = text(card(base({ address: "Davanagere, 577004", address_level: "partial" })));
  assert.ok(partial.includes("Davanagere, 577004 (partial address)"));
  const none = text(card(base({ address: null, address_level: "none" })));
  assert.ok(none.includes("Address not listed"));
  assert.ok(!/Hadadi|Davanagere/.test(none), "nothing is made up for a missing address");
});

test("phone and opening hours are shown only when the source gives them", () => {
  const bare = text(card(base()));
  assert.ok(bare.includes("Phone not listed"));
  assert.ok(!bare.includes("(as listed)"));
  const full = card(base({ phone: "+91 80 2286 8423", phone_link: "tel:+918022868423", opening_hours: "Mo-Sa 09:00-21:00" }));
  assert.ok(full.includes('href="tel:+918022868423"') && text(full).includes("Mo-Sa 09:00-21:00 (as listed)"));
  assert.ok(!text(full).includes("Phone not listed"));
});

// ---- old listings and warnings ---------------------------------------------------------------------------------------------------

test("an old listing says so next to its date; a recent one does not", () => {
  assert.equal(editedNote(base({ listing_old: true }), "13 Oct 2014"), "last edited 13 Oct 2014, more than 3 years ago, so it may be out of date");
  assert.equal(editedNote(base(), "14 Mar 2026"), "last edited 14 Mar 2026");
  assert.equal(editedNote(base(), null), null);
  const old = text(card(base({ listing_old: true, listing_last_edited: "2014-10-13" })));
  assert.ok(old.includes("last edited 13 Oct 2014, more than 3 years ago, so it may be out of date. Not verified."));
  const recent = text(card(base()));
  assert.ok(recent.includes("last edited 14 Mar 2026. Not verified.") && !recent.includes("out of date"));
});

test("the page keeps the community-data warning, the official locator link and the attribution", () => {
  const html = results(mixed);
  const out = text(html);
  for (const needle of ["edited by volunteers", "has not verified them", "incomplete, out of date or missing", "moved or closed", "Official Jan Aushadhi Kendra locator", "Store data © OpenStreetMap contributors"]) {
    assert.ok(out.includes(needle), needle);
  }
  assert.ok(html.includes('href="https://janaushadhi.gov.in/locate-kendra"'));
});

// ---- duplicates ------------------------------------------------------------------------------------------------------------------

const merged = base({ also_listed_as: [{ store_id: "osm:way/9", metres_apart: 40, reason: "the same name, 40 m apart, and nothing that differs" }] });

test("a store that absorbed a likely duplicate says so, names the other entry, and shows nothing from it", () => {
  const out = text(card(merged));
  assert.ok(out.includes("Treated as one store: OpenStreetMap also lists way 9 (the same name, 40 m apart, and nothing that differs). Nothing from the other entry is shown here."));
  assert.ok(!text(card(base())).includes("Treated as one store"));
  const two = text(card(base({ also_listed_as: [merged.also_listed_as[0], { store_id: "osm:node/10", metres_apart: 12, reason: "the same name, 12 m apart, and nothing that differs" }] })));
  assert.ok(two.includes("way 9 (") && two.includes("node 10 (") && two.includes("the other entries"));
});

test("the summary counts merged duplicates, in the singular and the plural, and says nothing when there are none", () => {
  assert.ok(text(results([merged], { duplicates_merged: 1 })).includes("1 likely duplicate OpenStreetMap entry was merged: same name, close together, and nothing that differs."));
  assert.ok(text(results([merged, base({ store_id: "osm:node/2" })], { duplicates_merged: 2 })).includes("2 likely duplicate OpenStreetMap entries were merged"));
  assert.ok(!text(results([base()], { duplicates_merged: 0 })).includes("duplicate"));
});

// ---- markers and the list ---------------------------------------------------------------------------------------------------------

function pins(html) {
  return [...html.matchAll(/<button[^>]*class="store-pin ([^"]*)"[^>]*data-category="([^"]*)"[^>]*aria-label="([^"]*)"[^>]*>(\d+)<\/button>/g)].map((m) => ({ classes: m[1], category: m[2], label: m[3], number: Number(m[4]) }));
}
const cards = (html) => [...html.matchAll(/<li class="store-card[^"]*" id="[^"]*" data-category="([^"]*)">/g)].map((m) => m[1]);

test("each kind of store has its own marker, the same on the map, in the key and on the card", () => {
  assert.deepEqual(MARKER_KINDS.map((k) => [k.category, k.className]), [["jan_aushadhi", "is-kendra"], ["generic", "is-generic"], ["pharmacy", "is-pharmacy"]]);
  assert.equal(new Set(MARKER_KINDS.map((k) => k.className)).size, 3);
  const found = pins(renderToStaticMarkup(h(StoreMap, { center: { lat: 14.464, lon: 75.922 }, stores: mixed, selectedRef: null, onSelect() {}, width: 640 })));
  assert.equal(found.length, 5);
  for (const pin of found) assert.ok(pin.classes.includes(markerKind(pin.category).className), `${pin.label}: ${pin.classes}`);
  assert.deepEqual(found.map((p) => p.category), ["pharmacy", "jan_aushadhi", "pharmacy", "generic", "pharmacy"]);
  assert.ok(found[1].label.includes("(Jan Aushadhi Kendra)") && found[3].label.includes("(Generic medicine store)") && found[0].label.includes("(Pharmacy)"));
});

test("the map and the list show exactly the same stores, in the same order, with the same numbers", () => {
  const html = results(mixed);
  const onMap = pins(html);
  const inList = cards(html);
  assert.equal(onMap.length, mixed.length);
  assert.equal(inList.length, mixed.length);
  assert.deepEqual(onMap.map((p) => p.number), [1, 2, 3, 4, 5]);
  assert.deepEqual(onMap.map((p) => p.category), inList, "pin i is the same kind as card i");
  assert.deepEqual(onMap.map((p) => p.label.match(/^Show (.*) \(/)[1]), mixed.map((s) => s.name), "pin i names the same store as card i");
});

test("the map key counts what is in the list, lists only the kinds present, and uses the same marker look", () => {
  assert.deepEqual(keyEntries(mixed).map((k) => [k.category, k.count]), [["jan_aushadhi", 1], ["generic", 1], ["pharmacy", 3]]);
  const html = renderToStaticMarkup(h(StoreMapKey, { stores: mixed }));
  const out = text(html);
  assert.ok(out.includes("Jan Aushadhi Kendra: 1") && out.includes("Generic medicine store: 1") && out.includes("Pharmacies: 3"), out);
  assert.ok(!out.includes("Pharmacys"), "plurals are real words");
  assert.ok(text(renderToStaticMarkup(h(StoreMapKey, { stores: [mixed[1], { ...mixed[1], store_id: "osm:node/22" }] }))).includes("Jan Aushadhi Kendras: 2"));
  for (const k of ["is-kendra", "is-generic", "is-pharmacy"]) assert.ok(html.includes(`store-key-pin ${k}`), k);
  assert.ok(!/store-key-pin[^>]*>\s*\d/.test(html), "a key swatch carries no number: it could be read as a store's number");
  const onlyKendras = renderToStaticMarkup(h(StoreMapKey, { stores: [mixed[1]] }));
  assert.ok(onlyKendras.includes("is-kendra") && !onlyKendras.includes("is-pharmacy") && !onlyKendras.includes("is-generic"));
  assert.equal(renderToStaticMarkup(h(StoreMapKey, { stores: [] })), "");
});

test("the selected store is the same one on the map and in the list", () => {
  const html = results(mixed, {}, { selectedRef: "osm:node/2" });
  const selectedPins = [...html.matchAll(/<button[^>]*class="store-pin [^"]*is-selected"[^>]*aria-label="Show ([^"(]*) \(/g)].map((m) => m[1].trim());
  const selectedCards = [...html.matchAll(/<li class="store-card is-selected"[^>]*>[\s\S]*?<strong[^>]*>([^<]*)<\/strong>/g)].map((m) => m[1]);
  assert.deepEqual(selectedPins, ["Pradhana Mantri Jan Aushadi Kendra"]);
  assert.deepEqual(selectedCards, ["Pradhana Mantri Jan Aushadi Kendra"]);
});

// ---- filters ---------------------------------------------------------------------------------------------------------------------

test("the category filters include Jan Aushadhi only, and each says what it keeps", () => {
  assert.deepEqual(SCOPE_OPTIONS.map((o) => o.key), ["all", "jan_aushadhi", "generic", "pharmacy"]);
  assert.deepEqual(SCOPE_OPTIONS.map((o) => o.label), [
    "All medical stores and Jan Aushadhi Kendras", "Jan Aushadhi Kendras only", "Jan Aushadhi Kendras and generic stores", "Other pharmacies only",
  ]);
  assert.equal(scopeNoun("jan_aushadhi"), "Jan Aushadhi Kendras");
  assert.equal(scopeNoun("nonsense"), "medical stores and Jan Aushadhi Kendras", "an unknown filter reads as all, never as a narrower one");
});

test("an empty result names the filter used and says only that none are listed, with a way out", () => {
  for (const [scope, phrase] of [["all", "No medical stores and Jan Aushadhi Kendras are listed within 5 km"], ["jan_aushadhi", "No Jan Aushadhi Kendras are listed within 5 km"],
    ["generic", "No Jan Aushadhi Kendras and generic stores are listed within 5 km"], ["pharmacy", "No pharmacies other than Jan Aushadhi Kendras are listed within 5 km"]]) {
    const html = results([], { scope });
    const out = text(html);
    assert.ok(out.includes(phrase), scope);
    assert.ok(out.includes("does not mean there are none") && out.includes("Official Jan Aushadhi Kendra locator"));
    assert.equal(out.includes("All medical stores and Jan Aushadhi Kendras”"), scope !== "all", `the hint to widen the filter appears only under a narrower one (${scope})`);
    assert.ok(!html.includes("store-map") && !html.includes("store-card") && !html.includes("store-key"));
  }
});

test("a store list under the Kendras-only filter shows only Kendra markers and cards", () => {
  const onlyKendras = [mixed[1], base({ store_id: "osm:node/8", name: "Jan Aushadhi Kendra No. 2", category: "jan_aushadhi", category_label: "Jan Aushadhi Kendra", lat: 14.47, distance_m: 600 })];
  const html = results(onlyKendras, { scope: "jan_aushadhi" });
  assert.deepEqual(pins(html).map((p) => p.category), ["jan_aushadhi", "jan_aushadhi"]);
  assert.deepEqual(cards(html), ["jan_aushadhi", "jan_aushadhi"]);
  assert.ok(text(html).includes("2 stores within 5 km"));
});

test("when the list is cut to the nearest stores, the page says how many there were", () => {
  const cut = text(results(mixed, { total_found: 33 }));
  assert.ok(cut.includes("5 stores within 5 km, nearest first. Showing the nearest 5 of 33: choose a smaller distance or a category to narrow the list."));
  assert.ok(!text(results(mixed, { total_found: 5 })).includes("Showing the nearest"), "a complete list is not called cut");
  assert.ok(!text(results(mixed)).includes("Showing the nearest"), "an older answer without the total says nothing about it");
});

