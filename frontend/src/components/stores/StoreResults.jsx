import { Clock, ExternalLink, MapPin, Navigation, Phone } from "lucide-react";
import StoreMap from "./StoreMap";
import { addressLine, categoryTone, editedNote, formatListingDate, keyEntries, markerKind, scopeNoun, storeDomId } from "../../utils/stores";

/** What the map's markers mean, counted from the stores in the list below it (so the key cannot disagree with them). */
export function StoreMapKey({ stores }) {
  const entries = keyEntries(stores);
  if (entries.length === 0) return null;
  return (
    <ul className="store-key" aria-label="Map key">
      {entries.map((k) => (
        <li key={k.category}>
          <span className={`store-pin store-key-pin ${k.className}`} aria-hidden="true" />
          {k.count === 1 ? k.label : k.plural}: {k.count}
        </li>
      ))}
    </ul>
  );
}

/** One store, exactly as listed: a missing name, address, phone or hours says it is not listed, never a placeholder that looks real. */
export function StoreCard({ store, number, selected, onSelect }) {
  const address = addressLine(store);
  const edited = editedNote(store, formatListingDate(store.listing_last_edited));
  const alsoListed = store.also_listed_as || [];
  return (
    <li className={`store-card ${selected ? "is-selected" : ""}`} id={storeDomId(store.store_id)} data-category={store.category}>
      <button type="button" className="store-card-head" onClick={() => onSelect?.(store.store_id)} aria-pressed={selected} aria-label={`Show ${store.name} on the map`}>
        <span className="store-number" aria-hidden="true">{number}</span>
        <span className="store-title">
          <strong className={store.name_listed === false ? "is-unnamed" : undefined}>{store.name}</strong>
          <span className={`pa-pill is-${categoryTone(store.category)}`}>{markerKind(store.category).label}</span>
        </span>
        <span className="store-distance num">{store.distance_text}</span>
      </button>
      <div className="store-body">
        <p className="small store-line">
          <MapPin size={14} aria-hidden="true" />
          {address.text ? <span>{address.text}{address.note && <span className="muted"> ({address.note})</span>}</span> : <span className="muted">Address not listed</span>}
        </p>
        <p className="small store-line"><Phone size={14} aria-hidden="true" /> {store.phone ? (store.phone_link ? <a href={store.phone_link}>{store.phone}</a> : store.phone) : <span className="muted">Phone not listed</span>}</p>
        {store.opening_hours && <p className="small store-line"><Clock size={14} aria-hidden="true" /> {store.opening_hours} <span className="muted">(as listed)</span></p>}
        <div className="row store-actions">
          <a className="btn btn-primary btn-sm" href={store.directions_url} target="_blank" rel="noopener noreferrer"><Navigation size={14} /> Directions</a>
          {store.website && <a className="btn btn-ghost btn-sm" href={store.website} target="_blank" rel="noopener noreferrer"><ExternalLink size={14} /> Website</a>}
        </div>
        <p className="tiny subtle">Listed on {store.source}{edited ? `, ${edited}` : ""}. Not verified.</p>
        {alsoListed.length > 0 && (
          <p className="tiny subtle">
            Treated as one store: OpenStreetMap also lists {alsoListed.map((o) => `${o.store_id.replace("osm:", "").replace("/", " ")} (${o.reason})`).join("; ")}. Nothing from the other entr{alsoListed.length === 1 ? "y" : "ies"} is shown here.
          </p>
        )}
      </div>
    </li>
  );
}

/**
 * The answer to a search, in the order a reader needs it: the notices, the map with its key, and then the list of stores at the bottom. Stores
 * only: nothing here knows about medicines, stock or prices.
 */
export default function StoreResults({ result, selectedRef, onSelect }) {
  const noun = scopeNoun(result.scope);
  const merged = result.duplicates_merged || 0;
  return (
    <div className="store-results">
      <div className="alert alert-warn" role="note"><div>{result.verification_note} <a href={result.official_locator_url} target="_blank" rel="noopener noreferrer">Official Jan Aushadhi Kendra locator</a></div></div>

      {result.count === 0 ? (
        <div className="state" role="status">
          <h3>No {noun} are listed within {result.radius_km} km</h3>
          <p>
            That only means OpenStreetMap lists none here. It does not mean there are none, because the listing is incomplete in many areas.
            Try a larger distance{result.scope !== "all" ? " or “All medical stores and Jan Aushadhi Kendras”" : ""}, or look on the official Jan Aushadhi Kendra locator.
          </p>
        </div>
      ) : (
        <>
          <p className="small" style={{ margin: 0 }}>
            <strong>{result.count}</strong> {result.count === 1 ? "store" : "stores"} within {result.radius_km} km, nearest first.
            {result.total_found > result.count && ` Showing the nearest ${result.count} of ${result.total_found}: choose a smaller distance or a category to narrow the list.`}
            {merged > 0 && ` ${merged} likely duplicate OpenStreetMap ${merged === 1 ? "entry was" : "entries were"} merged: same name, close together, and nothing that differs.`}
          </p>
          {result.may_be_incomplete && <p className="small subtle" style={{ margin: 0 }}>This area has a lot of listings, so some may be missing. Try a smaller distance to see the closest ones.</p>}
          <StoreMap center={result.center} stores={result.stores} selectedRef={selectedRef} onSelect={onSelect} />
          <StoreMapKey stores={result.stores} />
        </>
      )}
      <p className="tiny subtle" style={{ margin: 0 }}>{result.attribution} {result.location_note}</p>

      {result.count > 0 && (
        <section aria-label="Nearby medical stores">
          <h2 className="section-label">Nearby medical stores</h2>
          <ol className="store-list">
            {result.stores.map((s, i) => <StoreCard key={s.store_id} store={s} number={i + 1} selected={selectedRef === s.store_id} onSelect={onSelect} />)}
          </ol>
        </section>
      )}
    </div>
  );
}
