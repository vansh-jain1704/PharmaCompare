import { Info } from "lucide-react";

/**
 * Availability - what PharmaCompare can and cannot say.
 *
 * PharmaCompare has no pharmacy stock feed. Nothing in the database says whether anything is on a shelf,
 * so this never shows a stock level of any kind. The one real signal is the
 * dataset's discontinued flag, and that is the only status derived from data. Everything else reads
 * "not tracked".
 *
 * (An earlier version showed simulated readings generated from the medicine id. They were removed: a patient
 * can take a made-up stock reading as fact however small the demo tag beside it.)
 */
export default function AvailabilityStatus({ discontinued }) {
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

  return (
    <span className="availability">
      <span className="avail-row avail-unknown">
        <span className="avail-dot" />
        Availability is not tracked — confirm with your pharmacy
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
        <strong>Stock availability is not tracked.</strong>{" "}
        PharmaCompare has no pharmacy stock feed, so it cannot tell you whether any pharmacy has a medicine on its shelf.
        "Discontinued by manufacturer" is the one status taken from the reference dataset, which is a static snapshot
        and may be out of date. Always confirm with your pharmacy.
      </span>
    </div>
  );
}
