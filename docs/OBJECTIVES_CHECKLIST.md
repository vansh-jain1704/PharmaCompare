# PharmaCompare: status of the six Phase-2 objectives

Source of truth: the Phase-2 PPT and the synopsis. Reassessed 2026-10-18, after the work on objectives 1, 4 and 6. Status words mean:

- **Complete**: works end to end on real data in this repository, with tests.
- **Partially complete**: the working part is stated; the rest is named.
- **Blocked**: cannot be finished from inside this repository (needs an outside data source, partnership or measurement).

Nothing below claims live prices, live pharmacy stock, or a measured AI accuracy. None exists in this project.

| # | Objective | Status |
|---|---|---|
| 1 | Real-time drug price comparison | **Partially complete.** Provenance and "not live" labelling are done; a live price source is Blocked |
| 2 | AI-based prescription analysis | **Complete** for the pipeline; accuracy is not measured |
| 3 | Alternative drug recommendation engine | **Complete** (same-ingredient alternatives, with stated limits) |
| 4 | Real-time drug availability tracking | **Partially complete.** Receiving reports is done and tested; no pharmacy sends any, so no stock is known. Live inventory is Blocked |
| 5 | Confidence-based decision support | **Complete** (heuristic scores, not calibrated probabilities) |
| 6 | Healthcare data sources | **Partially complete.** Provenance, measured validation and service status are done; there are only two sources, neither authoritative |

## 1. Real-time drug price comparison: Partially complete

Gap found in the audit: each price carried a source and a date on the server, but the screen never showed them, the PDF only said "dataset snapshot"
in general, and the date is the day the snapshot was *imported here*, not the day a price was true.

Done (evidence):
- `price_provenance_service.py`: `reference_basis()` gives every reference price its source, its import date, its age and "Not a live price", and says the
  date is the import date; an old snapshot (`REFERENCE_PRICE_STALE_DAYS`, 180) is called old. `live_data_status()` counts, from the registry, whether any
  pharmacy feed has delivered anything: with none it says "No live pharmacy price or stock feed is connected". Demo data never counts as a feed.
- On screen: the line detail, the medicine drawer, the table footer (`PriceSources.jsx`), and the About page. In the PDF: "Where these prices come from".
- Pharmacy-reported prices stay separate, with pharmacy, age and feed (`offer_service.py`, `PharmacyOffers.jsx`), and are "reported", never "live".
- Tests: `tests/test_price_sources_and_partner_feed.py` (provenance, live status, payloads, PDF), `frontend/tests/sources.test.mjs`.

Remaining / Blocked: **no live price source is connected.** NPPA ceiling prices and the Jan Aushadhi list are published as PDFs / a search form (no API),
so they are reference data, not live. Neither has been downloaded: that needs the owner's explicit permission, and the Jan Aushadhi site's terms could
not be read. No public pharmacy price API is known to exist; scraping a retailer would breach its terms and is not done.

## 2. AI-based prescription analysis: Complete (accuracy not measured)

Working: upload (JPG/PNG/PDF) → Google Vision OCR (English and Hindi) with EasyOCR fallback → medicine matching with a strict safety stance (uncertain
lines stay "needs verification"; a similar name is never accepted on score alone) → dosage / frequency / duration reading (`instruction_service.py`) →
allergy and interaction checks (DDInter 2.0) → report on screen and PDF. Statuses are Matched / Suggested / Needs verification / Confirmed by you /
Entered by you. A person can type in a medicine the dataset lacks (`manual_entry_service.py`); instructions and Hindi notes are listed apart from the
medicines (`prescription_notes_service.py`); with no allergies saved the app says the check did not run.
Evidence: `tests/test_handwritten_prescription.py` (real captured OCR output of a handwritten prescription through the real pipeline),
`tests/test_verification_workflow.py`, `frontend/tests/handwriting.test.mjs`.

Remaining: handwriting accuracy is not measured on a labelled set, so no accuracy figure may be quoted. Four of the five brands on the tested
prescription are not in the dataset, so they stay unconfirmed by design.

## 3. Alternative drug recommendation engine: Complete

Working: alternatives share active ingredients at the same strength, dosage form and release type (database query); ordered by pack-comparable price;
each alternative shows per-unit price and manufacturer; the notes "How these were chosen", "Not compared", "safety checks carry over" and "ask your doctor
first" appear on screen and in the PDF (`recommendation_notes.py`); alternatives for an unsettled line are information only and add nothing to savings.

Remaining: the dataset says nothing about inactive ingredients, manufacturer quality or bioequivalence, so the app lists these as not compared.
It never advises switching.

## 4. Real-time drug availability tracking: Partially complete

Gap found in the audit: pharmacy-reported stock could arrive only through a CSV run by hand, and nothing showed when a feed last delivered.

Done (evidence):
- A keyed receiver: `POST /api/feeds/offers` (`routes/feeds.py`, `partner_feed_service.py`, `partner_key_model.py`, `database/manage_partner_keys.py`,
  table `Partner_Keys` with only a hash of each key). Rows are validated exactly like a CSV feed; rejected rows come back with reasons; size, row and rate
  limits; one 401 for every kind of bad key. Documented in `docs/PARTNER_FEED_API.md`.
- Freshness: each feed shows when its newest report was observed and when data last arrived (About page, `data_sources_service.list_sources`); stock
  older than 48 h and prices older than 7 days are marked old; the discontinued flag is labelled as dataset data.
- Checked end to end over HTTP: a key was created, one row accepted and one rejected with its reason, a bad key got 401, and the report appeared on the
  medicine's detail with its age and feed, apart from the reference price. The test feed was then removed.
- Tests: `tests/test_price_sources_and_partner_feed.py` (34 tests).

Remaining / Blocked: **no pharmacy sends reports and no inventory API is connected**, so no stock level is known today and the app says so. Receiving
reports is not the same as having a partner: that needs a pharmacy or distributor to be given a key and to send. Reports are only as fresh as the last push.
The rate window is held in the server process (see the API document).

## 5. Confidence-based decision support: Complete

Working: every line has a status with the reasons, the match score, the text-read confidence, closest guesses, conflict warnings, and a statement of what the
percentage means (similarity of the text to a dataset product, not the chance of being right). Low-confidence lines are never auto-confirmed; a person's
confirmation is recorded with the warnings shown.

Remaining: scores are heuristic and uncalibrated. A calibrated "AI confidence" would need a labelled evaluation set.

## 6. Healthcare data sources: Partially complete

Gap found in the audit: a registry with counts existed, but nothing validated the data product by product, and the app did not say which outside services
it depends on or what it does without them.

Done (evidence):
- Provenance and update time: `Data_Sources` registry (source, URL, licence as recorded or "not recorded", record count, when obtained, measured quality
  notes), shown on the About page and `/api/data-sources`; every reference price states its import date.
- Validation of names, strengths, forms and ingredients (`data_validation_service.py`): each product is checked against its own fields. Measured on
  all 253,973 products (`python database/validate_medicines.py`, read-only, about 17 s): 12,007 have at least one note, among them 387 with a strength in
  the name that could not be matched to the ingredient strengths, 6,187 with an incomplete ingredient list, 3,656 with no strength, 1,964 with no form, 4
  with no usable price. The form never disagreed with the name, because the dataset's form was derived from the name at import, so that check is a guard
  for a future source. Notes appear in search results, the medicine drawer, the report detail (identified lines only) and the PDF, and are labelled a
  reason to check, never a correction. The checks cover unit conversion (1.2 gm = 1200 mg) and ingredient totals; a bare brand number ("Pan 40") is not checked.
- Unavailable services and incomplete data: `external_services()` lists Google Vision, Gemini, OpenStreetMap and pharmacy feeds with whether each is
  configured (never a key) and what the app does without it; incomplete ingredient lists are never offered as equivalents; unavailable store listings
  say so instead of showing an empty list.
- Tests: `tests/test_data_validation.py` (22 tests, including counts checked against the database), `frontend/tests/sources.test.mjs`.

Remaining / Blocked: only two sources exist, and neither is authoritative. The medicine dataset is community-compiled and does not say where its data
came from; DDInter's licence is not recorded. No official register (CDSCO, NPPA, Jan Aushadhi) is integrated: those publish PDFs or search pages, and
downloading them needs the owner's permission. Agreement between fields of one dataset is not clinical verification. Nothing refreshes the datasets
automatically, and "configured" does not mean a service is up (nothing is pinged).

## Items from the PPT beyond the six objectives

| Item | Status | Evidence |
|---|---|---|
| Medicine Timeline | Complete | `timeline_service.py`, `MedicineTimeline.jsx`, PDF section; unread dosing is listed as "not read", never guessed |
| AI Confidence Score | Complete (heuristic) | see objective 5 |
| Gemini-based reports | Complete when `GEMINI_API_KEY` is set; deterministic otherwise | `report_summary_service.py` validates every sentence against the facts; the key is not set here, so the Gemini path was tested with a mocked response only |
| Medicine scanning | Complete (candidates only) | `scan_service.py`, `/scan` page; photo deleted after reading, nothing stored, never a confirmation |
| Stores (independent) | Complete as a location feature | `store_locator_service.py`, `/stores`; OpenStreetMap listings, not verified; knows nothing about medicines or stock |

## How to re-verify

```
cd backend
venv\Scripts\python.exe -m unittest discover -s tests -t .
venv\Scripts\python.exe database\validate_medicines.py
cd ..\frontend
npm run test:logic
npm run lint
npm run build
```
