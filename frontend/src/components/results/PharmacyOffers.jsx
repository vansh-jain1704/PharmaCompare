import { rupees } from "../../utils/format";

/**
 * What pharmacies have REPORTED for one medicine: price, stock, when, and which feed.
 *
 * Built by the backend (offer_service) from imported pharmacy reports and rendered as given. The dataset's reference price
 * is NOT a pharmacy offer and is never shown here. With no reports it says so; demo data is always labelled.
 */
export default function PharmacyOffers({ offers }) {
  if (!offers || !offers.count) {
    return (
      <p className="small muted">
        No pharmacy has reported a price or stock for this medicine. The reference price comes from a dataset snapshot, not from a pharmacy.
      </p>
    );
  }
  return (
    <div className="offers">
      {offers.has_demo_data && (
        <div className="alert alert-warn" role="note">
          <div><strong>Demo data.</strong> These are not real pharmacies and not real prices.</div>
        </div>
      )}
      <ul className="alts">
        {offers.items.map((item) => (
          <li key={`${item.pharmacy}-${item.city}-${item.observed_at}`}>
            <span>
              <strong>{item.pharmacy}</strong>
              <small>{[item.city, `reported ${item.age}`, item.source + (item.demo ? " (demo)" : "")].filter(Boolean).join(" · ")}</small>
              <small className={item.stock_stale && item.availability !== "unknown" ? "warn-text" : undefined}>
                {item.availability === "unknown" ? "Stock not stated" : item.availability_label}
                {item.availability !== "unknown" && item.stock_stale ? " (old report: may have changed)" : ""}
                {item.quantity_available != null ? ` · ${item.quantity_available} reported` : ""}
              </small>
            </span>
            <span className="alt-price">
              <b>{item.price != null ? rupees(item.price) : "No price"}</b>
              {item.price != null && item.price_stale && <em>old price</em>}
            </span>
          </li>
        ))}
      </ul>
      {offers.count > offers.items.length && <p className="tiny subtle">Showing {offers.items.length} of {offers.count} pharmacies.</p>}
      <p className="tiny subtle">Reported by the pharmacies and not checked by PharmaCompare. Prices and stock change: confirm with the pharmacy.</p>
    </div>
  );
}
