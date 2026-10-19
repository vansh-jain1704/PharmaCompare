/**
 * Where the prices on the page come from, and whether any live feed exists, as the server stated it (price_provenance_service).
 * A reference price is never live: its date is the day the dataset snapshot was imported, not when the price was true.
 */
export default function PriceSources({ basis, live }) {
  if (!basis && !live) return null;
  return (
    <div className="price-sources" role="note">
      {basis && (
        <p className="small" style={{ margin: 0 }}>
          <span className="pa-pill is-muted">Reference price · not live</span> {basis.label}
          {basis.what_the_date_means && <span className="tiny subtle"> The date is {basis.what_the_date_means}.</span>}
        </p>
      )}
      {live && (
        <p className="small" style={{ margin: "0.4rem 0 0" }}>
          <span className={`pa-pill ${live.live_feed_connected ? "is-ok" : "is-warn"}`}>{live.live_feed_connected ? "Pharmacy reports received" : "No live feed connected"}</span> {live.statement}
        </p>
      )}
    </div>
  );
}
