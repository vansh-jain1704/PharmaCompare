import { Info } from "lucide-react";

export const NO_STOCK_REPORT = "No pharmacy stock report — confirm with your pharmacy";

// the tone of each availability status the backend can report (the classes already exist in components.css)
const TONE = { in_stock: "avail-in", limited: "avail-low", mixed: "avail-low", out_of_stock: "avail-out", stale: "avail-unknown" };

/**
 * Availability - only what a pharmacy has actually REPORTED, with when.
 *
 * Nothing in the reference dataset says whether anything is on a shelf, so a stock status is shown ONLY when a pharmacy feed
 * has reported one (`offers`, built by the backend from the imported reports, with their age and source). The label comes from
 * the backend as given, so the wording about freshness ("last reported 4 days ago: may have changed") cannot be softened here.
 * The one status taken from the dataset itself is the discontinued flag. With neither, this says that no report exists.
 *
 * (An earlier version showed simulated readings generated from the medicine id. They were removed: a patient can take a
 * made-up stock reading as fact however small the demo tag beside it. Data loaded as a demo is labelled "Demo data".)
 */
export default function AvailabilityStatus({ discontinued, offers }) {
  if (discontinued) {
    return (
      <span className="availability">
        <span className="avail-row avail-out">
          <span className="avail-dot" />
          Discontinued by manufacturer
        </span>
      </span>
    );
  }

  const reported = offers?.availability;
  if (reported && reported.status !== "not_reported") {
    return (
      <span className="availability">
        <span className={`avail-row ${TONE[reported.status] || "avail-unknown"}`}>
          <span className="avail-dot" />
          {reported.label}
        </span>
        {offers.has_demo_data && <span className="tag tag-warning" style={{ marginLeft: "0.4rem" }}>Demo data</span>}
      </span>
    );
  }

  return (
    <span className="availability">
      <span className="avail-row avail-unknown">
        <span className="avail-dot" />
        {NO_STOCK_REPORT}
      </span>
    </span>
  );
}

/**
 * Sits above a group of medicines so the limit is stated once, prominently, rather than only in a tooltip.
 */
export function AvailabilityDisclaimer() {
  return (
    <div className="demo-banner">
      <Info size={14} style={{ flexShrink: 0, marginTop: 2 }} />
      <span>
        <strong>Stock is shown only where a pharmacy has reported it.</strong>{" "}
        A report carries the pharmacy, the time and the feed it came from, and an old report is labelled as possibly out of date.
        Where nothing is shown, no pharmacy has reported on that medicine, so check with your pharmacy.
        "Discontinued by manufacturer" is taken from the reference dataset, which is a static snapshot and may be out of date.
      </span>
    </div>
  );
}
