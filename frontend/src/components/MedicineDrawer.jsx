import { useEffect, useMemo } from "react";
import { Factory, Pill, Sparkles, TrendingDown, X } from "lucide-react";
import AvailabilityStatus from "./ui/AvailabilityStatus";
import { rupees } from "../utils/format";

const norm = (s) => (s || "").toLowerCase().replace(/\s+/g, " ").trim();

/**
 * Details for one medicine, with a price comparison against the other
 * results that share its exact composition. The comparison only uses the
 * results the search returned (the endpoint returns a limited set), so it
 * says so instead of claiming to have compared the whole catalogue.
 */
export default function MedicineDrawer({ medicine, results, query, onClose, onExplain }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [onClose]);

  const same = useMemo(() => {
    if (!medicine?.composition) return [];
    const key = norm(medicine.composition);
    return results
      .filter((m) => m.medicine_id !== medicine.medicine_id && norm(m.composition) === key && m.price != null && !m.is_discontinued)
      .sort((a, b) => a.price - b.price);
  }, [medicine, results]);

  if (!medicine) return null;
  const facts = [
    ["Composition", medicine.composition],
    ["Strength", medicine.strength],
    ["Form", medicine.form],
    ["Manufacturer", medicine.manufacturer],
    ["Pack size", medicine.pack_size],
  ];

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`Details for ${medicine.medicine_name}`} onClick={(e) => e.stopPropagation()}>
        <header className="drawer-head">
          <span className="drawer-icon"><Pill size={22} /></span>
          <div className="grow">
            <h2>{medicine.medicine_name}</h2>
            <p className="small muted">{[medicine.strength, medicine.form].filter(Boolean).join(" · ") || "Medicine details"}</p>
          </div>
          <button type="button" className="icon-btn is-bordered" onClick={onClose} aria-label="Close details"><X size={18} /></button>
        </header>

        <div className="drawer-price">
          <div>
            <span className="label">Reference price</span>
            <b className="num">{rupees(medicine.price)}</b>
          </div>
          {medicine.is_discontinued && <span className="pill tone-risk">Discontinued</span>}
        </div>

        <dl className="facts drawer-facts">
          {facts.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v || "Not on file"}</dd></div>)}
          <div><dt>Availability</dt><dd><AvailabilityStatus medicine={medicine} discontinued={medicine.is_discontinued} compact /></dd></div>
        </dl>

        <section className="drawer-section">
          <h3><TrendingDown size={16} /> Same composition, compared</h3>
          {same.length > 0 ? (
            <ul className="alts">
              {same.slice(0, 8).map((alt) => {
                const diff = medicine.price != null ? medicine.price - alt.price : null;
                const pct = diff != null && medicine.price > 0 ? (diff / medicine.price) * 100 : null;
                return (
                  <li key={alt.medicine_id}>
                    <span><strong>{alt.medicine_name}</strong><small><Factory size={11} /> {alt.manufacturer || "Maker not on file"}</small></span>
                    <span className="alt-price">
                      <b>{rupees(alt.price)}</b>
                      {pct != null && pct > 0 && <em>{pct.toFixed(0)}% less</em>}
                      {pct != null && pct < 0 && <em className="more">{Math.abs(pct).toFixed(0)}% more</em>}
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="small muted">No other product with this exact composition is in the current results for “{query}”. Search by the salt name to compare makers.</p>
          )}
          <p className="tiny subtle">Compared only against the results shown for your search, not the whole catalogue. Reference-dataset prices, not live pharmacy prices.</p>
        </section>

        <footer className="drawer-foot">
          <button type="button" className="btn btn-soft" onClick={() => onExplain(medicine)}><Sparkles size={15} /> Explain this medicine</button>
        </footer>
      </aside>
    </div>
  );
}
