# Stores: medical stores and Jan Aushadhi Kendras near me

An **independent, location-only feature**. Page: `/stores` (menu "Stores", dashboard card "Find Stores Near Me"). API: `POST /api/stores/nearby`,
`POST /api/stores/geocode` (both need a login). Code: `backend/app/services/store_locator_service.py`, `backend/app/routes/stores.py`,
`frontend/src/pages/StoreFinder.jsx`, `frontend/src/components/stores/`, `frontend/src/utils/stores.js`.

## What it does

1. Finds nearby medical stores and Jan Aushadhi Kendras from the person's current location (browser permission, asked only when the button is
   pressed) or from a typed area or PIN code.
2. Shows them on a map and as a list at the bottom of the page: name, kind, address, distance, directions and phone/website/hours where listed.
3. Filters: distance (2, 5, 10, 25 km) and category: "All medical stores and Jan Aushadhi Kendras" (default), "Jan Aushadhi Kendras only",
   "Jan Aushadhi Kendras and generic stores", or "Other pharmacies only". The map and the list always show the same stores.

## What it deliberately does not do

It does **not** search for medicines in stores, show medicine-specific stock, compare store prices, or connect store results to prescription
medicines. It imports nothing about medicines, prescriptions, prices, availability or recommendations, and none of that code uses it
(`tests/test_store_locator.py`, class `Independence`, and `frontend/tests/stores.test.mjs` check this). The offers/availability feature and
its importer are unchanged: an earlier experiment that linked stores to pharmacy stock reports (a `Pharmacies.place_ref` column) was removed
again, including from the live database (the table was empty).

## Where the data comes from

| Part | Provider | Terms | Key |
|---|---|---|---|
| Store listings | OpenStreetMap through an Overpass API server | ODbL: attribution shown on the page | none |
| Typed place or PIN code to a position | Nominatim, only when "Find place" is pressed | ODbL; identify the application, at most one request a second (the code waits) | none |
| Map pictures | OpenStreetMap tile server, loaded by the browser | light, attributed use | none |
| Directions | a plain Google Maps link the person opens; nothing is sent from the server | n/a | none |

No API key is required and none was added. No existing configuration had a places or maps provider; the Vision key was deliberately not reused.

### Why "The store listing service could not be reached" appeared, and what changed

The public Overpass servers are often busy. On 2026-10-18 `overpass-api.de` timed out, `overpass.kumi.systems` and `overpass.private.coffee`
returned errors, and `overpass.openstreetmap.fr` answered. The route and the provider were both checked: the backend route was fine and the
single configured server was failing. The app now tries several servers in turn (`OVERPASS_URL`, then `OVERPASS_FALLBACK_URLS`), skips a dead one
after 5 seconds, stops after `PLACES_TOTAL_BUDGET_SECONDS`, and only shows the error if every server fails. A real search for 577001 (Davanagere)
then returned 6 stores including one Jan Aushadhi Kendra.

Public servers are for light, human-operated use and their usage policies have not been reviewed here. **For anything beyond a demo, run your own
Overpass instance (or use a commercial places provider) and set `OVERPASS_URL`, and put a contact address in `PLACES_USER_AGENT`.**
A commercial provider such as Google Places would need a key, billing and a new adapter beside `fetch_overpass`; its terms generally require its
results to be shown on its own map, so the map component would need replacing too.

## Settings (all optional, in `backend/.env`)

| Setting | Default | Meaning |
|---|---|---|
| `PLACES_PROVIDER` | `osm_overpass` | `off` turns the feature off; the page says it is not set up |
| `OVERPASS_URL` | `overpass.openstreetmap.fr` | the first server tried |
| `OVERPASS_FALLBACK_URLS` | `overpass-api.de`, `overpass.kumi.systems` | comma-separated; tried in turn |
| `PLACES_TOTAL_BUDGET_SECONDS` | 40 | stop trying further servers after this long |
| `NOMINATIM_URL` | public Nominatim | place search |
| `PLACES_USER_AGENT` | `PharmaCompare/1.0 (...)` | add a contact address |
| `PLACES_TIMEOUT_SECONDS` | 20 | per request |
| `STORE_DEFAULT_RADIUS_KM` / `STORE_MAX_RADIUS_KM` | 5 / 25 | search distance |
| `STORE_MAX_RESULTS` / `STORE_FETCH_LIMIT` | 30 / 400 | stores shown / listings read |
| `STORE_CACHE_SECONDS` | 300 | the same area is not asked for again within this time |

## What is shown, and what is not claimed

- **Names.** The name is the one the listing carries (its name, then English name, official name, brand, then any other-language name). A listing
  with no name is shown as "Pharmacy — name unavailable", in italics; nothing is made up. Real searches showed this often: 4 of the 6 stores near
  577001 have no name in OpenStreetMap.
- **Addresses** are only what the listing says: street, locality (a bare block letter is labelled "Block G"), town, district, state and PIN code.
  A full address needs a street name, a locality or town, and a PIN code; anything less is marked "(partial address)", and none is "Address not listed".
- **Duplicates.** Two entries are treated as one store only on evidence, never because they are close: shops are often a few metres apart (a real
  search found two shops 4 m apart with different phone numbers). They must have the same name (ignoring case and punctuation), be within 25 m (two
  points) or 60 m (a point and a building outline), and contradict each other on nothing (different phone numbers, branch, reference, house number,
  street or PIN code keep them apart). Entries with no name are never merged. The kept entry is the one that says most; nothing is copied from the
  other, which is named on it ("Treated as one store: OpenStreetMap also lists ..."), and the summary says how many were merged. Real searches
  for three areas found none to merge.
- **Old listings.** A listing not edited for 3 years (`STORE_LISTING_OLD_DAYS`, a policy setting) says "more than 3 years ago, so it may be out of date".
- **Cut lists.** The page shows at most `STORE_MAX_RESULTS` (30) stores. When there are more within the distance it says so ("Showing the nearest 30
  of 235"); a real search for central Bengaluru found 235 within 5 km.
- **Markers.** Each kind has its own marker, by shape as well as colour (Jan Aushadhi Kendra: green square; generic store: amber circle; other
  pharmacy: purple pin), with a key counted from the list. In a crowded area pins overlap: there is no clustering.
- **Only listed stores.** A store appears only if OpenStreetMap lists it. A missing phone, address or hours says "not listed". Nothing is
  invented. An empty result says only that none are *listed*.
- **Coverage is thin in places.** For 577001 OpenStreetMap lists 6 pharmacies within 5 km, four of them without a name. A short or empty list does
  not mean there are no stores; the official Kendra locator (`janaushadhi.gov.in/locate-kendra`) is linked from the page.
- **Not verified.** "Jan Aushadhi Kendra" or "Generic medicine store" comes from the name or brand text a listing carries (anyone can edit it;
  real listings spell it "Jan Aushadi", "Pradhana Mantri" and so on, and the classifier handles those). Each listing shows when it was last edited.
- **Privacy.** The browser asks for the location only when the button is pressed; the person can type an area instead. The position is rounded to
  about 100 m in the browser and again on the server, travels in a POST body (so it is not in a URL or an access log), is not stored and is not
  logged. Tests check each of these.

## Tests

`backend/tests/test_store_locator.py` (mocked network) and `frontend/tests/stores.test.mjs`. Verified by hand in the browser: location
permission denied (real), typed PIN code with real place search and real store data, the distance and kind filters, the map and list, and a
provider failure. Not covered by automated tests: the live Overpass, Nominatim and tile servers.
