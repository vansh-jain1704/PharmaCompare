import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowUpDown, Factory, Pill, Search, SlidersHorizontal, X } from "lucide-react";
import Page from "../components/Page";
import MedicineDrawer from "../components/MedicineDrawer";
import ExplainDialog from "../components/ui/ExplainDialog";
import { AvailabilityDisclaimer } from "../components/ui/AvailabilityStatus";
import { EmptyState, ErrorState } from "../components/ui/States";
import { searchMedicines } from "../api/prescriptionApi";
import { getErrorMessage } from "../api/getErrorMessage";
import { rupees } from "../utils/format";

const SUGGESTIONS = ["Dolo 650", "Paracetamol", "Azee 500", "Pan-D", "Zerodol-P", "Amoxicillin"];
const PRICE_CAPS = [50, 100, 250, 500];
const SORTS = [
  { key: "relevance", label: "Best match" },
  { key: "price-asc", label: "Price: low to high" },
  { key: "price-desc", label: "Price: high to low" },
  { key: "name", label: "Name A–Z" },
];
const NO_FILTERS = { forms: [], maker: "", maxPrice: "", hideDiscontinued: false, sort: "relevance" };

/**
 * Medicine explorer. Search is by brand or salt (that is what the lookup
 * endpoint supports); the filters narrow the results that came back,
 * including by manufacturer. Everything shown is a real catalogue record.
 */
export default function MedicineSearch() {
  const [query, setQuery] = useState("");
  const [state, setState] = useState({ status: "idle" });
  const [filters, setFilters] = useState(NO_FILTERS);
  const [showFilters, setShowFilters] = useState(false);
  const [selected, setSelected] = useState(null);
  const [explaining, setExplaining] = useState(null);
  const inputRef = useRef(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) { setState({ status: "idle" }); return undefined; }
    let cancelled = false;
    setState({ status: "loading" });
    const handle = setTimeout(async () => {
      try {
        const res = await searchMedicines(term);
        if (!cancelled) { setState({ status: "ready", items: res.data.medicines, term }); setFilters(NO_FILTERS); }
      } catch (err) {
        if (!cancelled) setState({ status: "error", message: getErrorMessage(err) });
      }
    }, 300);
    return () => { cancelled = true; clearTimeout(handle); };
  }, [query]);

  const items = state.items || [];
  const forms = useMemo(() => [...new Set(items.map((m) => m.form).filter(Boolean))].sort(), [items]);
  const makers = useMemo(() => [...new Set(items.map((m) => m.manufacturer).filter(Boolean))].sort(), [items]);

  const visible = useMemo(() => {
    let list = items.filter((m) =>
      (filters.forms.length === 0 || filters.forms.includes(m.form)) &&
      (!filters.maker || m.manufacturer === filters.maker) &&
      (!filters.maxPrice || (m.price != null && m.price <= Number(filters.maxPrice))) &&
      (!filters.hideDiscontinued || !m.is_discontinued));
    if (filters.sort === "price-asc") list = [...list].sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity));
    if (filters.sort === "price-desc") list = [...list].sort((a, b) => (b.price ?? -Infinity) - (a.price ?? -Infinity));
    if (filters.sort === "name") list = [...list].sort((a, b) => a.medicine_name.localeCompare(b.medicine_name));
    return list;
  }, [items, filters]);

  const activeFilters = filters.forms.length + (filters.maker ? 1 : 0) + (filters.maxPrice ? 1 : 0) + (filters.hideDiscontinued ? 1 : 0);
  const toggleForm = (f) => setFilters((cur) => ({ ...cur, forms: cur.forms.includes(f) ? cur.forms.filter((x) => x !== f) : [...cur.forms, f] }));

  return (
    <Page
      crumbs={[{ label: "Dashboard", to: "/dashboard" }, { label: "Medicines" }]}
      eyebrow="Medicine explorer"
      title="Search medicines"
      subtitle="Look up any brand or salt: composition, maker, pack size and reference price."
    >
      <div className="search-bar rise d1">
        <Search size={19} className="subtle" aria-hidden="true" />
        <input
          ref={inputRef} type="search" value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by brand or salt, e.g. Dolo 650 or Paracetamol" aria-label="Search medicines"
        />
        {query && <button type="button" className="icon-btn" onClick={() => setQuery("")} aria-label="Clear search"><X size={17} /></button>}
      </div>

      {state.status === "idle" && (
        <div className="explore-idle rise d2">
          <div className="row" style={{ flexWrap: "wrap" }}>
            <span className="tiny subtle">Try</span>
            {SUGGESTIONS.map((s) => <button key={s} type="button" className="chip" onClick={() => setQuery(s)}>{s}</button>)}
          </div>
          <EmptyState icon={<Pill size={26} />} title="Search the medicine catalogue" message="Type at least two characters. Every result is a real catalogue record. Nothing is generated." />
        </div>
      )}

      {state.status === "loading" && <div className="med-grid" style={{ marginTop: "var(--s-5)" }}>{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 190 }} />)}</div>}
      {state.status === "error" && <section className="panel" style={{ marginTop: "var(--s-5)" }}><ErrorState message={state.message} /></section>}

      {state.status === "ready" && items.length === 0 && (
        <section className="panel" style={{ marginTop: "var(--s-5)" }}>
          <EmptyState title={`Nothing matches “${state.term}”`} message="Our dataset uses Indian brand names and salt spellings. Try the salt instead of the brand, or the other way round." />
        </section>
      )}

      {state.status === "ready" && items.length > 0 && (
        <div className="explore rise">
          <div className="explore-bar">
            <p className="small muted" style={{ margin: 0 }}><strong>{visible.length}</strong> of {items.length} result{items.length === 1 ? "" : "s"} for “{state.term}”</p>
            <div className="explore-controls">
              <label className="select-wrap" title="Sort results">
                <ArrowUpDown size={14} aria-hidden="true" />
                <select value={filters.sort} onChange={(e) => setFilters({ ...filters, sort: e.target.value })} aria-label="Sort results">
                  {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
                </select>
              </label>
              <button type="button" className={`btn btn-secondary btn-sm ${showFilters ? "is-on" : ""}`} aria-expanded={showFilters} onClick={() => setShowFilters((v) => !v)}>
                <SlidersHorizontal size={14} /> Filters{activeFilters > 0 && <span className="count">{activeFilters}</span>}
              </button>
            </div>
          </div>

          {showFilters && (
            <div className="filters pop">
              <div className="filter-group">
                <span className="label">Form</span>
                <div className="chip-grid">{forms.map((f) => <button key={f} type="button" className={`chip ${filters.forms.includes(f) ? "is-selected" : ""}`} onClick={() => toggleForm(f)}>{f}</button>)}</div>
              </div>
              <div className="filter-group">
                <span className="label">Price</span>
                <div className="chip-grid">
                  {PRICE_CAPS.map((c) => <button key={c} type="button" className={`chip ${String(filters.maxPrice) === String(c) ? "is-selected" : ""}`} onClick={() => setFilters({ ...filters, maxPrice: String(filters.maxPrice) === String(c) ? "" : String(c) })}>Under ₹{c}</button>)}
                </div>
              </div>
              <div className="filter-group">
                <span className="label">Manufacturer</span>
                <select className="input" value={filters.maker} onChange={(e) => setFilters({ ...filters, maker: e.target.value })} aria-label="Filter by manufacturer">
                  <option value="">All manufacturers</option>
                  {makers.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
              <label className="check">
                <input type="checkbox" checked={filters.hideDiscontinued} onChange={(e) => setFilters({ ...filters, hideDiscontinued: e.target.checked })} />
                Hide discontinued
              </label>
              {activeFilters > 0 && <button type="button" className="link-btn" onClick={() => setFilters({ ...NO_FILTERS, sort: filters.sort })}>Clear filters</button>}
            </div>
          )}

          <AvailabilityDisclaimer />

          {visible.length === 0 ? (
            <section className="panel"><EmptyState title="No results match these filters" message="Loosen a filter to see more." action={<button type="button" className="btn btn-secondary btn-sm" onClick={() => setFilters(NO_FILTERS)}>Clear filters</button>} /></section>
          ) : (
            <div className="med-grid">
              {visible.map((m, i) => (
                <button type="button" key={m.medicine_id} className={`med-card rise ${i < 6 ? `d${i % 5 + 1}` : ""}`} onClick={() => setSelected(m)} aria-label={`Open details for ${m.medicine_name}`}>
                  <span className="med-card-top">
                    <strong>{m.medicine_name}</strong>
                    {m.is_discontinued && <span className="pill tone-risk">Discontinued</span>}
                  </span>
                  <span className="med-comp">{m.composition || "Composition not on file"}</span>
                  <span className="med-meta">{[m.strength, m.form].filter(Boolean).join(" · ")}</span>
                  <span className="med-maker"><Factory size={12} /> {m.manufacturer || "Maker not on file"}</span>
                  <span className="med-bottom"><b className="num">{rupees(m.price)}</b><span className="med-more">Compare →</span></span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {selected && <MedicineDrawer medicine={selected} results={items} query={state.term} onClose={() => setSelected(null)} onExplain={setExplaining} />}
      {explaining && <ExplainDialog medicine={explaining} onClose={() => setExplaining(null)} />}
    </Page>
  );
}
