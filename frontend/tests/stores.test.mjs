// The Stores page: medical stores and Jan Aushadhi Kendras near a place. An independent, location-only feature.
// Covers the helpers, the map arithmetic, the page's controls, and what a store card and the results block say.
//
// The stores below are made-up test inputs for rendering. No store in this file exists.
//
//   npm run test:logic
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  AuthProvider, MAP_ATTRIBUTION, MemoryRouter, StoreCard, StoreFinder, StoreMap, StoreResults, TILE_URL, ThemeProvider, buildMapView, categoryTone, fitZoom,
  formatListingDate, geolocationMessage, project, roundCoordinate,
} from "../.test-build/entry.js";

const text = (html) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
const h = React.createElement;

const store = (over = {}) => ({
  store_id: "osm:node/1", name: "Test Jan Aushadhi Kendra", category: "jan_aushadhi", category_label: "Jan Aushadhi Kendra",
  address: "12 Test Road, Testville, 110001", lat: 28.615, lon: 77.21, distance_m: 150, distance_text: "150 m",
  phone: "+91 11 2345 6789", phone_link: "tel:+911123456789", website: null, opening_hours: null,
  directions_url: "https://www.google.com/maps/dir/?api=1&destination=28.615000,77.210000",
  source: "OpenStreetMap", listing_last_edited: "2026-03-14", verified: false,
  name_listed: true, address_level: "full", address_parts: { street: "12 Test Road", locality: null, town: "Testville", postcode: "110001" }, listing_old: false, also_listed_as: [], ...over,
});
const result = (over = {}) => ({
  center: { lat: 28.614, lon: 77.209 }, radius_km: 5, scope: "all", count: 3,
  stores: [
    store(),
    store({ store_id: "osm:node/2", name: "Test Medicals", category: "pharmacy", category_label: "Pharmacy", lat: 28.62, lon: 77.22, distance_text: "1.2 km", phone: null, phone_link: null, address: null }),
    store({ store_id: "osm:node/3", name: "Test Generic Store", category: "generic", category_label: "Generic medicine store", lat: 28.63, lon: 77.23, distance_text: "2.7 km" }),
  ],
  may_be_incomplete: false,
  attribution: "Store data © OpenStreetMap contributors (ODbL). Map tiles © OpenStreetMap contributors.",
  verification_note: "These stores come from OpenStreetMap, a map edited by volunteers. PharmaCompare has not verified them: a listing can be incomplete, out of date or missing, and a store may have moved or closed.",
  category_counts: { jan_aushadhi: 1, generic: 1, pharmacy: 1 }, duplicates_merged: 0,
  official_locator_url: "https://janaushadhi.gov.in/locate-kendra", location_note: "Your position was rounded to about 100 m for this search and is not stored.", ...over,
});
const resultsHtml = (props) => renderToStaticMarkup(h(StoreResults, { result: result(), selectedRef: null, onSelect: () => {}, ...props }));
// The theme provider reads the document while rendering, so a minimal stand-in is in place for the render only.
const pageHtml = () => {
  const had = Object.getOwnPropertyDescriptor(globalThis, "document");
  globalThis.document = { documentElement: { getAttribute: () => "light", setAttribute() {}, classList: { add() {}, remove() {} } } };
  try {
    return renderToStaticMarkup(h(MemoryRouter, null, h(ThemeProvider, null, h(AuthProvider, null, h(StoreFinder)))));
  } finally {
    if (had) Object.defineProperty(globalThis, "document", had); else delete globalThis.document;
  }
};

// ---- the page itself ---------------------------------------------------------------------------------------------------------

test("the page offers the location button, a typed area or PIN code, and the distance filters", () => {
  const html = pageHtml();
  const out = text(html);
  for (const needle of ["Find medical stores near me", "Use my current location", "Your browser will ask first", "not stored", "Or type an area, town or PIN code", "Find place"]) {
    assert.ok(out.includes(needle), needle);
  }
  for (const km of [2, 5, 10, 25]) assert.ok(html.includes(`>Within ${km} km<`), `${km} km`);
  assert.match(html, /<option value="5" selected="">Within 5 km<\/option>/, "5 km is the default distance");
  assert.match(html, /<option value="all" selected="">All medical stores and Jan Aushadhi Kendras<\/option>/, "every store is the default");
  for (const label of ["All medical stores and Jan Aushadhi Kendras", "Jan Aushadhi Kendras only", "Jan Aushadhi Kendras and generic stores", "Other pharmacies only"]) assert.ok(out.includes(label), label);
  assert.equal((html.match(/<option value="(all|jan_aushadhi|generic|pharmacy)"/g) || []).length, 4, "four category filters");
  assert.ok(!html.includes("store-card") && !html.includes("store-map"), "no results until a place is chosen");
});

test("the page has no medicine search, stock, price or prescription controls", () => {
  const out = text(pageHtml()).replace(/medical stores/gi, "stores");
  assert.ok(!/medicine|stock|prescription|price|availab/i.test(out), out.match(/.{20}(medicine|stock|prescription|price|availab).{20}/i)?.[0]);
  assert.ok(!pageHtml().includes('type="search" id="store-medicine"') && !pageHtml().includes("store-medicine"));
});

test("the Stores source files import nothing about medicines, prescriptions, prices or stock", () => {
  const files = ["src/pages/StoreFinder.jsx", "src/components/stores/StoreResults.jsx", "src/components/stores/StoreMap.jsx", "src/utils/stores.js"];
  for (const file of files) {
    const source = readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
    const imports = [...source.matchAll(/^import .* from "([^"]+)"/gm)].map((m) => m[1]).join(" ");
    for (const forbidden of ["medicine", "Medicine", "decisionTable", "summary", "vailability", "offers", "dosing"]) {
      assert.ok(!imports.includes(forbidden), `${file} imports ${forbidden}`);
    }
    // the project keeps every API call in one module; the Stores files may take only the two store calls from it
    for (const m of source.matchAll(/import \{([^}]*)\} from "[^"]*prescriptionApi"/g)) {
      assert.deepEqual(m[1].split(",").map((n) => n.trim()).filter(Boolean).sort(), ["findNearbyStores", "findPlace"].filter((n) => m[1].includes(n)), `${file} takes other calls from the API module`);
    }
    assert.ok(!/searchMedicines|getMedicineOffers|medicine_id|medicineId/.test(source), `${file} refers to a medicine`);
  }
});

// ---- helpers -----------------------------------------------------------------------------------------------------------------

test("the position is rounded to about 100 m before it is sent", () => {
  assert.equal(roundCoordinate(28.613912345), 28.614);
  assert.equal(roundCoordinate(-33.868821), -33.869);
  assert.equal(roundCoordinate("77.20908"), 77.209);
});

test("each way the browser can refuse a location has its own message and always offers typing a place", () => {
  const messages = [1, 2, 3, 0].map((code) => geolocationMessage({ code }));
  assert.equal(new Set(messages).size, 4);
  for (const m of messages) assert.match(m, /type your area or PIN code/i);
  assert.match(messages[0], /nothing was shared/);
  assert.equal(geolocationMessage(null), "");
});

test("category tones and listing dates", () => {
  assert.deepEqual(["jan_aushadhi", "generic", "pharmacy"].map(categoryTone), ["ok", "warn", "muted"]);
  assert.equal(formatListingDate("2026-03-14"), "14 Mar 2026");
  assert.equal(formatListingDate(null), null);
  assert.equal(formatListingDate("garbage"), null);
});

// ---- the map -----------------------------------------------------------------------------------------------------------------

test("web mercator: the origin, the antimeridian, and each zoom doubling the world", () => {
  assert.deepEqual(project(0, 0, 0), { x: 128, y: 128 });
  assert.equal(project(0, 180, 1).x, 512);
  assert.equal(project(0, 0, 3).x, 1024);
  assert.ok(project(28, 77, 5).y < project(10, 77, 5).y, "further north is nearer the top");
  assert.ok(Number.isFinite(project(90, 0, 4).y), "the poles are clamped, not infinite");
});

test("the map zooms out as the points spread apart and every point stays inside the frame", () => {
  const close = [{ lat: 28.614, lon: 77.209 }, { lat: 28.615, lon: 77.21 }];
  const far = [{ lat: 28.614, lon: 77.209 }, { lat: 28.7, lon: 77.3 }, { lat: 28.5, lon: 77.1 }];
  assert.ok(fitZoom(close, 640, 360) > fitZoom(far, 640, 360));
  for (const points of [close, far]) {
    for (const p of buildMapView(points, 640, 360).positions) assert.ok(p.x >= 0 && p.x <= 640 && p.y >= 0 && p.y <= 360, `${p.x},${p.y}`);
  }
});

test("the tiles cover the whole frame, come from the tile server and wrap correctly", () => {
  const view = buildMapView([{ lat: 28.614, lon: 77.209 }, { lat: 28.62, lon: 77.22 }], 640, 360);
  assert.ok(Math.min(...view.tiles.map((t) => t.left)) <= 0);
  assert.ok(Math.max(...view.tiles.map((t) => t.left + 256)) >= 640);
  assert.ok(Math.min(...view.tiles.map((t) => t.top)) <= 0);
  assert.ok(Math.max(...view.tiles.map((t) => t.top + 256)) >= 360);
  assert.equal(new Set(view.tiles.map((t) => t.key)).size, view.tiles.length);
  for (const t of view.tiles) assert.match(t.url, new RegExp(`^${TILE_URL.replace(/[.]/g, "\\.")}/${view.zoom}/\\d+/\\d+\\.png$`));
  const edge = buildMapView([{ lat: 0, lon: 179.9999 }, { lat: 0, lon: -179.9999 }], 640, 360);
  assert.ok(edge.tiles.every((t) => Number(t.url.split("/").at(-2)) < 2 ** edge.zoom), "near the antimeridian the tile column wraps");
});

test("positions keep their order and carry the extra fields; no points means no map", () => {
  const view = buildMapView([{ lat: 1, lon: 1, kind: "you" }, { lat: 1.001, lon: 1.001, kind: "store", number: 1 }], 640, 360);
  assert.deepEqual(view.positions.map((p) => p.kind), ["you", "store"]);
  assert.equal(view.positions[1].number, 1);
  assert.deepEqual(buildMapView([], 640, 360), { zoom: null, tiles: [], positions: [] });
  assert.deepEqual(buildMapView([{ lat: 1, lon: 1 }], 0, 360).tiles, []);
  assert.equal(buildMapView([{ lat: 1, lon: 1 }], 640, 360).zoom, 15);
});

test("the map numbers its pins like the list and marks the person's own position", () => {
  const html = renderToStaticMarkup(h(StoreMap, { center: { lat: 28.614, lon: 77.209 }, stores: result().stores, selectedRef: null, onSelect: () => {}, width: 640 }));
  assert.ok(html.includes("store-pin is-you"));
  assert.ok(html.includes("Show Test Jan Aushadhi Kendra (Jan Aushadhi Kendra), number 1 in the list"));
  assert.ok(html.includes("Show Test Generic Store (Generic medicine store), number 3 in the list"));
  assert.ok(html.includes(MAP_ATTRIBUTION));
  assert.ok(html.includes(`src="${TILE_URL}/`));
});

// ---- a store card ------------------------------------------------------------------------------------------------------------

test("a store card shows what is listed: name, kind, distance, address, phone, directions, source and that it is not verified", () => {
  const out = text(renderToStaticMarkup(h(StoreCard, { store: store(), number: 1 })));
  for (const needle of ["Test Jan Aushadhi Kendra", "Jan Aushadhi Kendra", "150 m", "12 Test Road, Testville, 110001", "+91 11 2345 6789", "Directions", "Listed on OpenStreetMap", "last edited 14 Mar 2026", "Not verified"]) {
    assert.ok(out.includes(needle), needle);
  }
});

test("a store card links the phone and directions safely", () => {
  const html = renderToStaticMarkup(h(StoreCard, { store: store({ website: "https://example.invalid/store" }), number: 1 }));
  assert.ok(html.includes('href="tel:+911123456789"'));
  assert.ok(html.includes('href="https://www.google.com/maps/dir/?api=1&amp;destination=28.615000,77.210000"'));
  for (const tag of html.match(/<a [^>]*target="_blank"[^>]*>/g)) assert.match(tag, /rel="noopener noreferrer"/);
  assert.equal((html.match(/target="_blank"/g) || []).length, 2, "directions and website open in a new tab, nothing else does");
});

test("missing details say they are not listed rather than showing a placeholder", () => {
  const out = text(renderToStaticMarkup(h(StoreCard, { store: store({ address: null, phone: null, phone_link: null, listing_last_edited: null }), number: 2 })));
  assert.ok(out.includes("Address not listed"));
  assert.ok(out.includes("Phone not listed"));
  assert.ok(!out.includes("last edited"));
  assert.ok(!out.includes("Open now") && !out.includes("Open 24"), "opening hours are never invented");
});

test("opening hours are shown only when listed, marked as listed", () => {
  const out = text(renderToStaticMarkup(h(StoreCard, { store: store({ opening_hours: "Mo-Sa 09:00-21:00" }), number: 1 })));
  assert.ok(out.includes("Mo-Sa 09:00-21:00 (as listed)"));
});

// ---- the results -------------------------------------------------------------------------------------------------------------

test("the results show the notices, then the map, then the stores, nearest first", () => {
  const html = resultsHtml();
  const out = text(html);
  assert.ok(out.indexOf("has not verified them") < out.indexOf("3 stores within 5 km, nearest first"));
  assert.equal((html.match(/class="store-card ?(?:is-selected)?"/g) || []).length, 3);
  assert.ok(out.indexOf("Test Jan Aushadhi Kendra") < out.indexOf("Test Medicals") && out.indexOf("Test Medicals") < out.indexOf("Test Generic Store"));
  assert.ok(html.includes('href="https://janaushadhi.gov.in/locate-kendra"') && out.includes("Official Jan Aushadhi Kendra locator"));
  assert.ok(out.includes("Store data © OpenStreetMap contributors") && out.includes("not stored"));
});

test("the list of nearby stores is at the bottom, after the map and the attribution", () => {
  const html = resultsHtml();
  const listAt = html.indexOf('aria-label="Nearby medical stores"');
  assert.ok(listAt > 0);
  assert.ok(listAt > html.indexOf("store-map"), "below the map");
  assert.ok(listAt > html.indexOf("Store data"), "below the attribution");
  assert.ok(!html.slice(html.lastIndexOf("</ol>")).includes("store-map"), "nothing map-related follows the list");
  assert.ok(text(html.slice(html.lastIndexOf("</ol>"))).trim() === "", "the list is the last thing in the results");
});

test("the count reads correctly for one store and for several", () => {
  assert.ok(text(resultsHtml()).includes("3 stores within 5 km"));
  assert.ok(text(resultsHtml({ result: result({ count: 1, stores: [store()] }) })).includes("1 store within 5 km"));
  assert.ok(!text(resultsHtml({ result: result({ count: 1, stores: [store()] }) })).includes("1 stores"));
});

test("an empty area says only that none are listed, not that none exist, and shows no map or list", () => {
  const html = resultsHtml({ result: result({ count: 0, stores: [] }) });
  const out = text(html);
  assert.ok(out.includes("No medical stores and Jan Aushadhi Kendras are listed within 5 km"));
  assert.ok(out.includes("does not mean there are none"));
  assert.ok(!html.includes("store-map") && !html.includes("store-card") && !out.includes("Nearby medical stores"));
  const generic = text(resultsHtml({ result: result({ count: 0, stores: [], scope: "generic" }) }));
  assert.ok(generic.includes("No Jan Aushadhi Kendras and generic stores are listed") && generic.includes("All medical stores"));
});

test("an incomplete area is stated when the server says so", () => {
  assert.ok(text(resultsHtml({ result: result({ may_be_incomplete: true }) })).includes("some may be missing"));
});

test("the selected store is marked on the map and in the list", () => {
  const html = resultsHtml({ selectedRef: "osm:node/2" });
  assert.equal((html.match(/store-pin is-[a-z]+ is-selected/g) || []).length, 1);
  assert.equal((html.match(/class="store-card is-selected"/g) || []).length, 1);
});

test("no screen text calls a store verified, and none mentions stock, medicine or price", () => {
  const out = text(resultsHtml());
  assert.ok(!/verified/i.test(out.replace(/Not verified|has not verified them/g, "")), out.match(/.{20}verified.{20}/i)?.[0]);
  assert.ok(!/\bstock\b|prescription|price|availab/i.test(out), out.match(/.{20}(stock|prescription|price|availab).{20}/i)?.[0]);
});
