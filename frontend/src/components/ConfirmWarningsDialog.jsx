import { AlertTriangle } from "lucide-react";

/**
 * Shown when the person picks a product that clearly conflicts with what the prescription line says (a different
 * name, form, strength, ingredient or release type). The backend refuses to save such a choice until it is
 * acknowledged, and sends the conflicts in plain language; this puts them in front of the person.
 *
 * "Confirm anyway" records that THEY chose the product. It is never presented as proof that the product is
 * the one on the prescription, or that it is medically equivalent to it.
 */
export default function ConfirmWarningsDialog({ open, rawText, medicineName, warnings = [], saving, onBack, onConfirmAnyway }) {
  if (!open) return null;
  const conflicts = warnings.filter((w) => w.severity === "conflict");
  const notes = warnings.filter((w) => w.severity !== "conflict");

  return (
    <div className="modal-overlay" onClick={saving ? undefined : onBack}>
      <div className="modal-card picker-card" onClick={(e) => e.stopPropagation()} role="alertdialog" aria-modal="true" aria-labelledby="confirm-warnings-title">
        <div className="modal-icon modal-icon-danger"><AlertTriangle size={22} /></div>
        <h3 id="confirm-warnings-title">Check this before you confirm</h3>
        <p className="picker-rawtext">
          Your prescription line reads <strong>“{rawText}”</strong> and you chose <strong>“{medicineName}”</strong>. They differ:
        </p>

        <ul className="bullets" style={{ margin: "0.75rem 0" }}>
          {conflicts.map((w) => <li key={w.code}>{w.text}</li>)}
        </ul>
        {notes.length > 0 && (
          <ul className="bullets small muted" style={{ margin: "0 0 0.75rem" }}>
            {notes.map((w) => <li key={w.code}>{w.text}</li>)}
          </ul>
        )}

        <div className="alert alert-info" role="note">
          If you have checked the original prescription and this is the product it names, you can confirm. Confirming
          only records your decision. PharmaCompare has not verified that this product matches the prescription or
          that it is medically equivalent.
        </div>

        <div className="modal-actions" style={{ marginTop: "1rem" }}>
          <button type="button" className="btn btn-secondary" onClick={onBack} disabled={saving}>Go back</button>
          <button type="button" className="btn btn-primary" onClick={onConfirmAnyway} disabled={saving}>
            {saving ? "Saving..." : "Confirm anyway — I checked my prescription"}
          </button>
        </div>
      </div>
    </div>
  );
}
