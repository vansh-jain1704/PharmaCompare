// Bundling entry for the logic tests: the pure functions the analysis page is built on.
export { buildDecisionRows, summarizeSavings, rowStatus, confidenceText } from "../src/utils/decisionTable.js";
export { summarizeDetail } from "../src/utils/summary.js";
// The availability wording (rendered to static markup in the tests).
export { default as AvailabilityStatus, AvailabilityDisclaimer } from "../src/components/ui/AvailabilityStatus.jsx";
// The manual verification dialog (rendered to static markup in the tests).
export { default as MedicinePickerDialog } from "../src/components/MedicinePickerDialog.jsx";
