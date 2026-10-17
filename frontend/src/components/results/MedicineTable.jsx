import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { RotateCcw } from "lucide-react";
import { buildDecisionRows, rowStatus, confidenceText } from "../../utils/decisionTable";
import { SEVERITY_META, ISSUE_TYPE_LABELS } from "../../utils/medicineDisplay";
import { rupees } from "../../utils/format";
import { correctDetectedMedicine, addMedicineManually, removeDetectedMedicine } from "../../api/prescriptionApi";
import { getErrorMessage } from "../../api/getErrorMessage";
import MedicinePickerDialog from "../MedicinePickerDialog";
import ExplainDialog from "../ui/ExplainDialog";
import AvailabilityStatus from "../ui/AvailabilityStatus";
import { EmptyState, ErrorState } from "../ui/States";

/** Placeholder with the table's shape, shown while the analysis loads. */
export function MedicineTableSkeleton({ rows = 3 }) {
  return (
    <div className="pa-skel" aria-busy="true" aria-label="Loading medicines">
      {Array.from({ length: rows }).map((_, i) => <div className="skeleton" key={i} />)}
    </div>
  );
}

function Detail({ row, editable, saving, busy, onUseOption, onConfirm, onEdit, onRemove, onExplain }) {
  const med = row.doctorMedicine;
  const guess = row.guessedMedicine;
  const confirmed = row.status === "user_confirmed";
  return (
    <div className="detail">
      {row.allergyAlert && (
        <div className="detail-allergy" role="alert">
          <div><strong>Allergy alert</strong><p>{row.allergyAlertText}</p></div>
        </div>
      )}

      <div className="detail-grid">
        <section>
          <h4 className="detail-h">About this medicine</h4>
          {med ? (
            <dl className="facts">
              <div><dt>Composition</dt><dd>{med.composition || "Not on file"}</dd></div>
              <div><dt>Strength</dt><dd>{row.strength || "Not on file"}</dd></div>
              <div><dt>Form</dt><dd>{row.form || "Not on file"}</dd></div>
              <div><dt>Release</dt><dd>{row.releaseLabel ? row.releaseLabel[0].toUpperCase() + row.releaseLabel.slice(1) : "Conventional (not modified-release)"}</dd></div>
              <div><dt>Manufacturer</dt><dd>{med.manufacturer || "Not on file"}</dd></div>
              <div><dt>Pack</dt><dd>{med.pack_size || "Not on file"}</dd></div>
              <div><dt>Availability</dt><dd><AvailabilityStatus medicine={med} discontinued={med.is_discontinued} compact /></dd></div>
            </dl>
          ) : (
            <p className="small muted">{row.needsDisambiguation
              ? "We did not pick a product for this line: more than one fits. Choose one under \"Possible products\", or use Verify to search."
              : "We could not identify this line, so there are no medicine details yet. Use Verify to say which medicine it is."}</p>
          )}
          {med && row.brandUnspecified && (
            <p className="tiny subtle">The prescription names the ingredients but no brand, so any brand with this composition fits. The product shown is one example.</p>
          )}
        </section>

        <section>
          <h4 className="detail-h">Why we matched it</h4>
          <p className="small">{row.whyReason}</p>
          <p className="tiny subtle">Read from your prescription as <code>{row.rawText}</code></p>
          {!med && guess && <p className="tiny subtle">Closest guess: {guess.medicine_name} (not confirmed).</p>}
          {row.needsDisambiguation && row.matchOptions.length > 0 && (
            <div className="close-matches">
              <h5>{med ? "Close matches" : "Possible products"}</h5>
              <ul>
                {row.matchOptions.map((opt) => {
                  const current = med && opt.medicine_id === med.medicine_id;
                  return (
                    <li key={opt.medicine_id}>
                      <span><strong>{opt.medicine_name}</strong><small>{[opt.strength, opt.form, opt.release_type ? "modified release" : null, opt.manufacturer].filter(Boolean).join(" · ")}</small></span>
                      {current ? <span className="badge badge-muted">Current</span>
                        : editable && <button type="button" className="btn btn-secondary btn-sm" disabled={saving} onClick={() => onUseOption(opt)}>Use this</button>}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </section>

        <section>
          <h4 className="detail-h">Price &amp; alternatives</h4>
          {med && row.brandUnspecified ? (
            <p className="small muted">No brand is named on the prescription, so we do not compare prices against one product. Confirm a specific product to see its price and alternatives.</p>
          ) : med && row.priceReliable ? (
            <>
              <dl className="facts">
                <div><dt>Reference price</dt><dd>{rupees(row.prescribedPrice)}</dd></div>
                {row.topAlternative && <div><dt>Cheapest comparable option</dt><dd>{rupees(row.topAlternative.price)}</dd></div>}
                {row.priceNote && <div><dt>Note</dt><dd className="small">{row.priceNote}</dd></div>}
                {row.savingAmount > 0 && <div><dt>You could save</dt><dd className="ok-text strong">{rupees(row.savingAmount)}{row.savingPercent != null && ` (${row.savingPercent.toFixed(0)}%)`}</dd></div>}
              </dl>
              {row.allAlternatives.length > 0 ? (
                <ul className="alts">
                  {row.allAlternatives.slice(0, 4).map((alt) => (
                    <li key={alt.medicine_id}>
                      <span>
                        <strong>{alt.medicine_name}</strong>
                        <small>{[alt.manufacturer, alt.pack_size, !alt.same_pack_quantity ? "different pack size" : null].filter(Boolean).join(" · ")}</small>
                        {alt.price_flag_note && <small className="warn-text">{alt.price_flag_note}</small>}
                      </span>
                      <span className="alt-price"><b>{rupees(alt.price)}</b>{alt.counts_for_savings && alt.savings_percent > 0 && <em>{alt.savings_percent.toFixed(0)}% less</em>}</span>
                    </li>
                  ))}
                </ul>
              ) : <p className="small muted">No comparable alternatives on file.</p>}
              {row.allAlternatives.length > 0 && !row.topAlternative && <p className="tiny subtle">None of these is counted as a saving: each is in a different pack size, has a price that needs checking, or is not cheaper.</p>}
              {row.recommendations[0]?.reason && <p className="tiny subtle">{row.recommendations[0].reason}</p>}
            </>
          ) : (
            <p className="small muted">{med ? "No reliable reference price is on file for this medicine, so we do not estimate savings." : "Prices appear once the medicine is identified."}</p>
          )}
        </section>
      </div>

      {med && (
        <section className="detail-safety">
          <h4 className="detail-h">Safety for this medicine</h4>
          <div className="safety-lines">
            <p className="safety-line"><span><strong>Verification:</strong> {row.verificationLabel}</span></p>
            <p className="safety-line"><span><strong>Interactions:</strong> {row.interactionLabel}</span></p>
          </div>
          {row.relevantFindings.length > 0 && (
            <ul className="findings-list">
              {row.relevantFindings.map((f, i) => {
                const meta = SEVERITY_META[f.severity] || { label: f.severity, className: "badge-muted" };
                return (
                  <li key={i} className="finding-item is-notable">
                    <div className="finding-header"><strong>{ISSUE_TYPE_LABELS[f.issue_type] || f.issue_type}</strong><span className={`badge ${meta.className}`}>{meta.label}</span></div>
                    <p className="finding-explanation">{f.explanation}</p>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}

      <div className="detail-actions">
        {editable && med && !confirmed && <button type="button" className="btn btn-primary btn-sm" onClick={onConfirm} disabled={saving || busy}>Confirm this match</button>}
        {med && <button type="button" className="btn btn-secondary btn-sm" onClick={onExplain}>Explain this medicine</button>}
        {editable && med && <button type="button" className="btn btn-secondary btn-sm" onClick={onEdit}>Edit</button>}
        {editable && <button type="button" className="btn btn-ghost btn-sm danger-text" onClick={onRemove} disabled={busy}>{busy ? "Removing…" : "Remove"}</button>}
      </div>
    </div>
  );
}

/**
 * The medicine comparison table: one row per detected line.
 *
 *   # | Medicine (from prescription) | Strength / Form | Match status |
 *   Reference price | Alternative price | Savings | Action
 *
 * "Reference price" is the matched product's price in the imported dataset
 * and "Alternative price" is the cheapest comparable same-ingredient product
 * the backend found. Neither is a live pharmacy price. Safety wording is NOT
 * in the row; it lives in the opened row so the table stays scannable.
 */
export default function MedicineTable({ detail, prescriptionId, onCorrected, loading = false, error: loadError = null, onRetry }) {
  const [openId, setOpenId] = useState(null);
  const [pickerRow, setPickerRow] = useState(null);
  const [explaining, setExplaining] = useState(null);
  const [saving, setSaving] = useState(false);
  const [removingId, setRemovingId] = useState(null);
  const [actionError, setActionError] = useState("");

  if (loading) return <MedicineTableSkeleton />;
  if (loadError) {
    return (
      <ErrorState
        title="Something went wrong while loading medicines."
        message={typeof loadError === "string" ? loadError : undefined}
        action={onRetry && <button type="button" className="btn btn-primary btn-sm" onClick={onRetry}><RotateCcw size={14} /> Try again</button>}
      />
    );
  }

  const rows = buildDecisionRows(detail || {});
  const canEdit = prescriptionId != null && typeof onCorrected === "function";

  async function confirmMedicine(medicine, targetRow = pickerRow) {
    setSaving(true);
    setActionError("");
    try {
      if (targetRow === "new") await addMedicineManually(prescriptionId, medicine.medicine_id);
      else await correctDetectedMedicine(prescriptionId, targetRow.id, medicine.medicine_id);
      setPickerRow(null);
      await onCorrected();
    } catch (err) {
      setActionError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function removeRow(row) {
    setRemovingId(row.id);
    setActionError("");
    try {
      await removeDetectedMedicine(prescriptionId, row.id);
      await onCorrected();
    } catch (err) {
      setActionError(getErrorMessage(err));
    } finally {
      setRemovingId(null);
    }
  }

  const picker = (
    <MedicinePickerDialog
      open={!!pickerRow}
      rawText={pickerRow === "new" ? null : pickerRow?.rawText}
      currentName={pickerRow === "new" ? null : pickerRow?.doctorMedicine?.medicine_name}
      suggestions={pickerRow && pickerRow !== "new" && Array.isArray(pickerRow.matchOptions) ? pickerRow.matchOptions : []}
      saving={saving}
      onCancel={() => setPickerRow(null)}
      onConfirm={confirmMedicine}
    />
  );

  if (rows.length === 0) {
    return (
      <>
        <EmptyState
          title="No medicines detected."
          message="If you have just uploaded a prescription and nothing was read, you can add its medicines by hand and the rest of the analysis will run on them."
          action={
            <div className="row" style={{ flexWrap: "wrap", justifyContent: "center" }}>
              <Link to="/upload" className="btn btn-primary btn-sm">Analyze a prescription</Link>
              {canEdit && <button type="button" className="btn btn-secondary btn-sm" onClick={() => setPickerRow("new")}>Add a medicine</button>}
            </div>
          }
        />
        {picker}
      </>
    );
  }

  const toggle = (id) => setOpenId((cur) => (cur === id ? null : id));

  return (
    <div className="pa-table-wrap">
      {actionError && <div className="alert alert-risk" role="alert">{actionError}</div>}

      <table className="pa-table">
        <thead>
          <tr>
            <th className="col-n">#</th>
            <th>Medicine (from prescription)</th>
            <th>Strength / Form</th>
            <th>Match status</th>
            <th>Reference price</th>
            <th>Alternative price</th>
            <th>Savings</th>
            <th className="col-action">Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const med = row.doctorMedicine;
            const status = rowStatus(row);
            const open = openId === row.id;
            const editable = canEdit && typeof row.id === "number";
            const busy = removingId === row.id;
            const priced = med && row.priceReliable;
            return (
              <Fragment key={row.id}>
                <tr className={`pa-row ${status.tone === "warn" ? "is-attn" : ""} ${open ? "is-open" : ""}`}>
                  <td className="col-n" data-label="#">{index + 1}</td>

                  <td className="col-med" data-label="Medicine">
                    <strong>{med ? med.medicine_name : row.rawText}</strong>
                    <span className="sub">{med ? (row.rawText && row.rawText !== med.medicine_name ? `(${row.rawText})` : "") : (row.needsDisambiguation ? "(Choose which product)" : "(Could not be identified)")}</span>
                    {med && row.brandUnspecified && <span className="sub">Generic name - any brand</span>}
                  </td>

                  <td data-label="Strength / Form">
                    <div className="val">{med ? (<><span>{row.strength || "—"}</span><span className="sub">{row.form || ""}</span>{row.releaseLabel && <span className="sub">{row.releaseLabel}</span>}</>) : "—"}</div>
                  </td>

                  <td data-label="Match status">
                    <div className="val">
                      <span className={`pa-pill is-${status.tone}`}>{status.text}</span>
                      <span className="sub">{confidenceText(row)}</span>
                      {row.ocrUncertain && <span className="sub">Text read with low confidence</span>}
                      {row.allergyAlert && <span className="pa-pill is-risk" title={row.allergyAlertText || "Allergy alert"}>Allergy alert</span>}
                    </div>
                  </td>

                  <td data-label="Reference price">
                    <div className="val">{priced ? (<>{row.topAlternative ? <s>{rupees(row.prescribedPrice)}</s> : rupees(row.prescribedPrice)}{row.priceNote && <span className="sub" title={row.priceNote}>Unusual price</span>}</>) : <span className="muted">{med && row.brandUnspecified ? "Brand not named" : "Not available"}</span>}</div>
                  </td>

                  <td data-label="Alternative price">
                    <div className="val">
                      {priced && row.topAlternative && !row.priceFlag ? (
                        <>
                          <b>{rupees(row.topAlternative.price)}</b>
                          <span className="sub" title={row.topAlternative.medicine_name}>{row.topAlternative.medicine_name}</span>
                        </>
                      ) : "—"}
                    </div>
                  </td>

                  <td data-label="Savings">
                    {row.savingAmount > 0 ? (
                      <span className="pa-save">
                        <b>{row.savingPercent != null ? `${row.savingPercent.toFixed(0)}% lower` : "Lower"}</b>
                        <span>Save {rupees(row.savingAmount)}</span>
                      </span>
                    ) : (
                      <span className="pa-save is-none">{priced ? "No comparable saving" : (med && row.brandUnspecified ? "Brand not named" : "Price not available")}</span>
                    )}
                  </td>

                  <td className="col-action" data-label="Action">
                    {editable && !med && (
                      <button type="button" className="btn btn-primary btn-sm" onClick={() => { setActionError(""); setPickerRow(row); }} disabled={busy || saving}>
                        Verify
                      </button>
                    )}
                    <button type="button" className={`btn btn-sm ${med ? "btn-secondary" : "btn-ghost"}`} aria-expanded={open} onClick={() => toggle(row.id)}>
                      {open ? "Hide" : "View"}
                    </button>
                  </td>
                </tr>

                {open && (
                  <tr className="pa-detail-row">
                    <td colSpan={8}>
                      <Detail
                        row={row} editable={editable} saving={saving} busy={busy}
                        onUseOption={(opt) => confirmMedicine({ medicine_id: opt.medicine_id }, row)}
                        onConfirm={() => confirmMedicine({ medicine_id: med.medicine_id }, row)}
                        onEdit={() => { setActionError(""); setPickerRow(row); }}
                        onRemove={() => removeRow(row)}
                        onExplain={() => setExplaining(med)}
                      />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>

      <div className="pa-table-foot">
        <p>Not a replacement for your doctor's prescription. Prices are reference-dataset figures, not live pharmacy prices.</p>
        {canEdit && <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setActionError(""); setPickerRow("new"); }}>Add a medicine</button>}
      </div>

      {explaining && <ExplainDialog medicine={explaining} onClose={() => setExplaining(null)} />}
      {picker}
    </div>
  );
}
