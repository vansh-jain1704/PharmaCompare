// Bundling entry for the logic tests: the pure functions the analysis page is built on.
export { buildDecisionRows, summarizeSavings, rowStatus, confidenceText, CONFIDENCE_EXPLANATION } from "../src/utils/decisionTable.js";
export { summarizeDetail } from "../src/utils/summary.js";
// The availability wording (rendered to static markup in the tests).
export { default as AvailabilityStatus, AvailabilityDisclaimer } from "../src/components/ui/AvailabilityStatus.jsx";
// The manual verification dialog (rendered to static markup in the tests).
export { default as MedicinePickerDialog } from "../src/components/MedicinePickerDialog.jsx";
// The review flow: the conflict warnings, and the table with its opened detail panel.
export { default as ConfirmWarningsDialog } from "../src/components/ConfirmWarningsDialog.jsx";
export { default as MedicineTable, Detail } from "../src/components/results/MedicineTable.jsx";
// The Medicine Timeline and the one-sentence dosing reading.
export { default as MedicineTimeline } from "../src/components/results/MedicineTimeline.jsx";
export { dosingSentence } from "../src/utils/dosing.js";
// What pharmacies have reported (price, stock, age, source).
export { default as PharmacyOffers } from "../src/components/results/PharmacyOffers.jsx";
// The data-source registry as the About page lists it.
export { DataSourcesList } from "../src/components/DataSources.jsx";
// What the photo checks found.
export { default as PhotoQualityNotes } from "../src/components/PhotoQualityNotes.jsx";
// The on-request plain-language summary.
export { default as ReportSummary, SummaryView } from "../src/components/results/ReportSummary.jsx";
// The result of scanning a medicine pack.
export { ScanResults } from "../src/pages/ScanMedicine.jsx";
// How the alternatives were chosen and what is not compared.
export { default as AlternativesNotes } from "../src/components/results/AlternativesNotes.jsx";
// The Stores page (medical stores and Jan Aushadhi Kendras near a place): the pure helpers, the card, the results block and the page.
export { project, fitZoom, buildMapView, roundCoordinate, geolocationMessage, categoryTone, formatListingDate, TILE_URL, MAP_ATTRIBUTION } from "../src/utils/stores.js";
export { default as StoreResults, StoreCard } from "../src/components/stores/StoreResults.jsx";
export { default as StoreMap } from "../src/components/stores/StoreMap.jsx";
export { default as StoreFinder } from "../src/pages/StoreFinder.jsx";
export { AuthProvider } from "../src/context/AuthContext.jsx";
export { MemoryRouter } from "react-router-dom";
export { ThemeProvider } from "../src/context/ThemeContext.jsx";
// The handwritten-prescription review: statuses, notes, allergy notice and typing a medicine in.
export { default as StatusLegend } from "../src/components/results/StatusLegend.jsx";
export { STATUS_MEANINGS } from "../src/utils/statusMeanings.js";
export { default as PrescriptionNotes, AllergyNotice } from "../src/components/results/PrescriptionNotes.jsx";
export { default as EnterDetailsDialog } from "../src/components/EnterDetailsDialog.jsx";
export { initialDetails, detailsProblem } from "../src/utils/entryDetails.js";
// Objectives 1, 4 and 6: where prices come from, live versus reference, data notes, data sources and outside services.
export { default as PriceSources } from "../src/components/results/PriceSources.jsx";
export { default as DataNotes } from "../src/components/results/DataNotes.jsx";
export { hasWarning } from "../src/utils/dataNotes.js";
export { normalizePriceComparison } from "../src/utils/medicineDisplay.js";
export { ExternalServices } from "../src/components/DataSources.jsx";
// Buy Generic: the search link built from verified ingredients, strength and form, and the control beside a medicine's name.
export { productBuyGeneric, rowBuyGeneric, parseComposition, BUY_GENERIC_NOTE, SEARCH_BASE, MAX_QUERY_CHARS } from "../src/utils/buyGeneric.js";
export { default as BuyGenericButton, VerifyFirstNote } from "../src/components/BuyGenericButton.jsx";
export { default as MedicineResultCard } from "../src/components/MedicineResultCard.jsx";
export { default as MedicineDrawer } from "../src/components/MedicineDrawer.jsx";
// Stores: the filters, the marker kinds and key, and how an address and an old listing are put into words.
export { SCOPE_OPTIONS, scopeNoun, MARKER_KINDS, markerKind, keyEntries, addressLine, editedNote } from "../src/utils/stores.js";
export { StoreMapKey } from "../src/components/stores/StoreResults.jsx";

