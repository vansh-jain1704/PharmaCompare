import { useState } from "react";
import { X } from "lucide-react";
import { ENTRY_FORMS, EMPTY_DETAILS, detailsProblem } from "../utils/entryDetails";

/**
 * For a line the dataset cannot identify (a brand that is not in it): the person types the medicine as they read it from the prescription.
 * It is saved as "Entered by you" and never matched, priced or safety-checked. Nothing is pre-filled from a guess.
 */
export default function EnterDetailsDialog({ open, rawText, initial, saving, error, onCancel, onSave }) {
  const [details, setDetails] = useState(initial || EMPTY_DETAILS);
  const [touched, setTouched] = useState(false);
  if (!open) return null;

  const problem = detailsProblem(details);
  const set = (key) => (e) => setDetails((d) => ({ ...d, [key]: e.target.value }));

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <form
        className="modal-card picker-card"
        role="dialog"
        aria-modal="true"
        aria-label="Enter the medicine yourself"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => { e.preventDefault(); setTouched(true); if (!problem) onSave(details); }}
      >
        <div className="picker-header">
          <div>
            <h3>Enter the medicine yourself</h3>
            <p className="picker-rawtext">Read from your prescription: “{rawText}”</p>
          </div>
          <button type="button" className="picker-close" onClick={onCancel} aria-label="Close"><X size={18} /></button>
        </div>

        <div className="alert alert-warn" role="note">
          <div>
            Type what is written on your prescription. It is kept exactly as you type it and shown as “Entered by you”. It is not matched to
            the medicine dataset, so no price, saving, alternative or medicine-specific safety check is shown for it.
          </div>
        </div>

        <div className="field">
          <label htmlFor="entry-name">Medicine name</label>
          <input id="entry-name" type="text" value={details.name} onChange={set("name")} maxLength={100} autoComplete="off" required />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))", gap: "var(--s-4)" }}>
          <div className="field">
            <label htmlFor="entry-strength">Strength (optional)</label>
            <input id="entry-strength" type="text" value={details.strength} onChange={set("strength")} maxLength={40} placeholder="e.g. 500 mg" autoComplete="off" />
          </div>
          <div className="field">
            <label htmlFor="entry-form">Form (optional)</label>
            <select id="entry-form" value={details.form} onChange={set("form")}>
              <option value="">Not sure</option>
              {ENTRY_FORMS.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="entry-schedule">Schedule (optional)</label>
            <input id="entry-schedule" type="text" value={details.schedule} onChange={set("schedule")} maxLength={100} placeholder="e.g. 0-1-0 or once weekly" autoComplete="off" />
          </div>
          <div className="field">
            <label htmlFor="entry-duration">Duration (optional)</label>
            <input id="entry-duration" type="text" value={details.duration} onChange={set("duration")} maxLength={100} placeholder="e.g. 30 days or 8 weeks" autoComplete="off" />
          </div>
        </div>

        {touched && problem && <p className="field-error" role="alert">{problem}</p>}
        {error && <div className="alert alert-error" role="alert">{error}</div>}

        <div className="modal-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={saving}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? "Saving..." : "Save details"}</button>
        </div>
      </form>
    </div>
  );
}
