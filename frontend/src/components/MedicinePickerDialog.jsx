import { useEffect, useRef, useState } from "react";
import { Search, Check, X } from "lucide-react";
import { searchMedicines } from "../api/prescriptionApi";
import { getErrorMessage } from "../api/getErrorMessage";

// Release types the dataset knows (the backend sends a readable `release_label` for search results; the
// suggestions stored on a line carry only the code, so both are shown the same way).
const RELEASE_LABELS = {
  sr: "Sustained release",
  er: "Extended release",
  cr: "Controlled release",
  pr: "Prolonged release",
  mr: "Modified release",
  dt: "Dispersible",
  odt: "Mouth-dissolving",
  chewable: "Chewable",
  ec: "Enteric coated",
  modified: "Modified release",
};

function releaseLabel(medicine) {
  if (medicine.release_label) return medicine.release_label[0].toUpperCase() + medicine.release_label.slice(1);
  return medicine.release_type ? RELEASE_LABELS[medicine.release_type] || "Modified release" : null;
}

/**
 * One product, described the same way wherever it is listed: name, what it contains, strength and form, and
 * the things that make two look-alike products different (release type, discontinued, partial ingredient list).
 * Choosing one only SELECTS it - nothing is saved until the person presses the confirm button.
 */
function MedicineChoice({ medicine, selected, onSelect }) {
  const release = releaseLabel(medicine);
  return (
    <button
      type="button"
      className={`picker-result ${selected ? "is-selected" : ""}`}
      aria-pressed={selected}
      onClick={() => onSelect(medicine)}
    >
      <span className="picker-result-main">
        <strong>{medicine.medicine_name}</strong>
        {medicine.composition && <span className="picker-result-meta">Contains: {medicine.composition}</span>}
        <span className="picker-result-meta">
          {[medicine.strength, medicine.form, medicine.manufacturer].filter(Boolean).join(" · ")}
        </span>
        {(release || medicine.is_discontinued || medicine.composition_incomplete) && (
          <span style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
            {release && <span className="tag tag-warning">{release}</span>}
            {medicine.is_discontinued && <span className="tag tag-warning">Discontinued</span>}
            {medicine.composition_incomplete && <span className="tag tag-warning">Ingredient list incomplete</span>}
          </span>
        )}
      </span>
      {selected && <Check size={16} />}
    </button>
  );
}

/**
 * "This isn't the right medicine" picker.
 *
 * No matcher will ever be perfect on handwriting, so an unconfirmed or
 * wrong line has to be fixable by the person holding the prescription.
 * Results come straight from the Medicines table - this searches what is
 * on file and never offers anything that isn't.
 *
 * `suggestions` are the products the reader found for this line when it could not choose between them.
 * They are listed first, labelled as not confirmed, and selecting one still needs the confirm button.
 * `reasons` say, in plain language, why the line was not settled. `initialSelection` preselects one product
 * (still unconfirmed). `onMarkUnmatched` lets the person say the line is none of these.
 */
export default function MedicinePickerDialog({
  open, rawText, currentName, suggestions = [], reasons = [], initialSelection = null,
  onCancel, onConfirm, onMarkUnmatched, onEnterDetails, saving,
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [fallbackNote, setFallbackNote] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setResults([]);
    setSelected(initialSelection || null);
    setError("");
    setFallbackNote("");
    setLoading(false);
    const id = setTimeout(() => inputRef.current?.focus(), 50);
    return () => clearTimeout(id);
  }, [open, initialSelection]);   // the parent keeps `initialSelection` in state, so this runs on open or when another product is preselected

  // Debounced so typing doesn't fire a request per keystroke.
  useEffect(() => {
    if (!open) return undefined;
    const term = query.trim();
    if (term.length < 2) {
      setResults([]);
      setFallbackNote("");
      setLoading(false);                 // no search is running: a cancelled earlier one must not leave "Searching..." behind
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    const handle = setTimeout(async () => {
      try {
        const res = await searchMedicines(term);
        if (!cancelled) {
          setResults(res.data.medicines);
          setFallbackNote(res.data.fallback ? res.data.fallback_note || "" : "");
          setError("");
        }
      } catch (err) {
        if (!cancelled) setError(getErrorMessage(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [query, open]);

  if (!open) return null;

  const searching = query.trim().length >= 2;
  const showSuggestions = !searching && Array.isArray(suggestions) && suggestions.length > 0;

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-card picker-card" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="picker-header">
          <div>
            <h3>{rawText ? "Which medicine is this?" : "Add a medicine"}</h3>
            {rawText ? (
              <p className="picker-rawtext">Read from your prescription: “{rawText}”</p>
            ) : (
              <p className="picker-rawtext">
                For a medicine on your prescription that wasn't picked up from the image.
              </p>
            )}
            {currentName && <p className="picker-current">Currently recorded as: {currentName}</p>}
          </div>
          <button type="button" className="picker-close" onClick={onCancel} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="picker-search">
          <Search size={16} />
          <input
            ref={inputRef}
            type="text"
            placeholder="Search by brand or salt, e.g. Dolo, Pan-D or Vitamin D3 60000"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        {error && <div className="alert alert-error">{error}</div>}

        {reasons.length > 0 && !searching && (
          <div className="alert alert-warn" role="note">
            <div>
              <strong>Why this line needs your check</strong>
              <ul className="bullets" style={{ margin: "0.3rem 0 0" }}>
                {reasons.map((reason) => <li key={reason}>{reason}</li>)}
              </ul>
            </div>
          </div>
        )}
        {fallbackNote && searching && <div className="alert alert-warn" role="note">{fallbackNote}</div>}

        <div className="picker-results">
          {showSuggestions && (
            <>
              <p className="picker-rawtext" style={{ fontWeight: 600 }}>Suggested for this line (not confirmed)</p>
              <p className="picker-rawtext">
                These products fit what was read from your prescription. Pick the one that matches your prescription
                (check the strength, form and release type), then confirm. Or search for another.
              </p>
              {suggestions.map((m) => (
                <MedicineChoice key={`s-${m.medicine_id}`} medicine={m} selected={selected?.medicine_id === m.medicine_id} onSelect={setSelected} />
              ))}
            </>
          )}
          {loading && <p className="page-subtitle">Searching...</p>}
          {!loading && searching && results.length === 0 && !error && (
            <p className="page-subtitle">
              No medicine on file matches “{query.trim()}”. Try the salt name instead of the brand.
            </p>
          )}
          {!loading && !searching && !showSuggestions && (
            <p className="page-subtitle">Type at least 2 characters to search.</p>
          )}
          {results.map((m) => (
            <MedicineChoice key={m.medicine_id} medicine={m} selected={selected?.medicine_id === m.medicine_id} onSelect={setSelected} />
          ))}
        </div>

        <p className="picker-rawtext" style={{ marginBottom: "0.75rem" }}>
          Confirming records your choice. It does not prove that this is the medicine on your prescription, or that it is
          medically equivalent to it.
        </p>
        <div className="modal-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={saving}>
            Cancel
          </button>
          {rawText && typeof onEnterDetails === "function" && (
            <button type="button" className="btn btn-secondary" onClick={() => onEnterDetails()} disabled={saving}>
              Enter details yourself
            </button>
          )}
          {rawText && typeof onMarkUnmatched === "function" && (
            <button type="button" className="btn btn-secondary" onClick={() => onMarkUnmatched()} disabled={saving}>
              None of these
            </button>
          )}
          <button
            type="button"
            className="btn btn-primary"
            disabled={!selected || saving}
            onClick={() => onConfirm(selected)}
          >
            {saving ? "Saving..." : rawText ? "Confirm medicine" : "Add medicine"}
          </button>
        </div>
      </div>
    </div>
  );
}
