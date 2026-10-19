/**
 * Helpers for the Stores page (medical stores and Jan Aushadhi Kendras near a place). All pure, so the wording and the map arithmetic are
 * tested without a browser. Nothing here knows about medicines, stock or prices.
 */

const TILE = 256;
// OpenStreetMap's own tile server. Its usage policy allows light, attributed use; a busier deployment should use its own tile provider.
export const TILE_URL = "https://tile.openstreetmap.org";
export const MAP_ATTRIBUTION = "© OpenStreetMap contributors";

// The category filters. `noun` is how the results are described under that filter.
export const SCOPE_OPTIONS = [
  { key: "all", label: "All medical stores and Jan Aushadhi Kendras", noun: "medical stores and Jan Aushadhi Kendras" },
  { key: "jan_aushadhi", label: "Jan Aushadhi Kendras only", noun: "Jan Aushadhi Kendras" },
  { key: "generic", label: "Jan Aushadhi Kendras and generic stores", noun: "Jan Aushadhi Kendras and generic stores" },
  { key: "pharmacy", label: "Other pharmacies only", noun: "pharmacies other than Jan Aushadhi Kendras" },
];

export function scopeNoun(scope) {
  return (SCOPE_OPTIONS.find((o) => o.key === scope) || SCOPE_OPTIONS[0]).noun;
}

// One marker style per kind of store, the same on the map, in the key and on each card, so a pin can be matched to its listing by shape and colour
// as well as by number.
export const MARKER_KINDS = [
  { category: "jan_aushadhi", label: "Jan Aushadhi Kendra", plural: "Jan Aushadhi Kendras", className: "is-kendra" },
  { category: "generic", label: "Generic medicine store", plural: "Generic medicine stores", className: "is-generic" },
  { category: "pharmacy", label: "Pharmacy", plural: "Pharmacies", className: "is-pharmacy" },
];

export function markerKind(category) {
  return MARKER_KINDS.find((k) => k.category === category) || MARKER_KINDS[2];
}

/** How many of each kind the LIST holds, in the key's order (only kinds that are present). Counted from the stores shown, so the key cannot disagree with them. */
export function keyEntries(stores) {
  return MARKER_KINDS.map((k) => ({ ...k, count: stores.filter((s) => markerKind(s.category).category === k.category).length })).filter((k) => k.count > 0);
}

/** What to say about a store's address: the text and, when only part of an address is listed, a note. `text` is null when none is listed. */
export function addressLine(store) {
  const text = store.address || null;
  if (!text) return { text: null, note: null };
  return { text, note: store.address_level === "partial" ? "partial address" : null };
}

/** How the listing's last edit is described: the date, and when it is old, that it may be out of date. */
export function editedNote(store, formattedDate) {
  if (!formattedDate) return null;
  return store.listing_old ? `last edited ${formattedDate}, more than 3 years ago, so it may be out of date` : `last edited ${formattedDate}`;
}

/** The id of a store card's element, so a pin on the map can scroll its card into view. */
export function storeDomId(storeId) {
  return `store-${storeId.replace(/[^a-z0-9]/gi, "-")}`;
}

/** About 100 m. The position is rounded here, before it leaves the browser, as well as on the server. */
export function roundCoordinate(value) {
  return Math.round(Number(value) * 1000) / 1000;
}

/** Wording for each way the browser can fail to give a position. The person can always type a place instead. */
export function geolocationMessage(error) {
  if (!error) return "";
  if (error.code === 1) return "Location permission was declined, so nothing was shared. You can type your area or PIN code below instead.";
  if (error.code === 2) return "Your device could not work out where it is. Try again, or type your area or PIN code below.";
  if (error.code === 3) return "Finding your location took too long. Try again, or type your area or PIN code below.";
  return "Your location could not be read. You can type your area or PIN code below.";
}

export function categoryTone(category) {
  return category === "jan_aushadhi" ? "ok" : category === "generic" ? "warn" : "muted";
}

export function formatListingDate(iso) {
  if (!iso) return null;
  const [y, m, d] = String(iso).split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

// --- the map: Web Mercator tiles --------------------------------------------------------------------------------------------

export function project(lat, lon, zoom) {
  const scale = TILE * 2 ** zoom;
  const sin = Math.sin((Math.max(-85.0511, Math.min(85.0511, lat)) * Math.PI) / 180);
  return { x: ((lon + 180) / 360) * scale, y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale };
}

/** The largest zoom at which every point fits inside width x height with `padding` pixels to spare. */
export function fitZoom(points, width, height, padding = 48, minZoom = 3, maxZoom = 17) {
  for (let zoom = maxZoom; zoom > minZoom; zoom -= 1) {
    const projected = points.map((p) => project(p.lat, p.lon, zoom));
    const xs = projected.map((p) => p.x);
    const ys = projected.map((p) => p.y);
    if (Math.max(...xs) - Math.min(...xs) <= width - 2 * padding && Math.max(...ys) - Math.min(...ys) <= height - 2 * padding) return zoom;
  }
  return minZoom;
}

/**
 * Everything needed to draw the map: which tiles, where each point sits. `points` are {lat, lon, ...}; extra fields are carried through
 * on `positions` in the same order.
 */
export function buildMapView(points, width, height, padding = 48) {
  if (!points.length || !(width > 0) || !(height > 0)) return { zoom: null, tiles: [], positions: [] };
  const zoom = points.length === 1 ? 15 : fitZoom(points, width, height, padding);
  const projected = points.map((p) => project(p.lat, p.lon, zoom));
  const centreX = (Math.min(...projected.map((p) => p.x)) + Math.max(...projected.map((p) => p.x))) / 2;
  const centreY = (Math.min(...projected.map((p) => p.y)) + Math.max(...projected.map((p) => p.y))) / 2;
  const originX = centreX - width / 2;
  const originY = centreY - height / 2;
  const tilesAcross = 2 ** zoom;
  const tiles = [];
  for (let ty = Math.floor(originY / TILE); ty <= Math.floor((originY + height) / TILE); ty += 1) {
    if (ty < 0 || ty >= tilesAcross) continue;
    for (let tx = Math.floor(originX / TILE); tx <= Math.floor((originX + width) / TILE); tx += 1) {
      const wrapped = ((tx % tilesAcross) + tilesAcross) % tilesAcross;
      tiles.push({ key: `${zoom}/${tx}/${ty}`, url: `${TILE_URL}/${zoom}/${wrapped}/${ty}.png`, left: Math.round(tx * TILE - originX), top: Math.round(ty * TILE - originY) });
    }
  }
  const positions = points.map((p, i) => ({ ...p, x: Math.round(projected[i].x - originX), y: Math.round(projected[i].y - originY) }));
  return { zoom, tiles, positions };
}
