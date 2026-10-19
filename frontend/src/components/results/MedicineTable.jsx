import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { RotateCcw } from "lucide-react";
import { buildDecisionRows, rowStatus, confidenceText, CONFIDENCE_EXPLANATION } from "../../utils/decisionTable";
import { SEVERITY_META, ISSUE_TYPE_LABELS } from "../../utils/medicineDisplay";
import { rupees } from "../../utils/format";
import { dosingSentence } from "../../utils/dosing";
import { correctDetectedMedicine, addMedicineManually, removeDetectedMedicine, markMedicineUnmatched, enterMedicineDetails } from "../../api/prescriptionApi";
import { getErrorMessage } from "../../api/getErrorMessage";
import MedicinePickerDialog from "../MedicinePickerDialog";
import ConfirmWarningsDialog from "../ConfirmWarningsDialog";
import EnterDetailsDialog from "../EnterDetailsDialog";
import { initialDetails } from "../../utils/entryDetails";
import ExplainDialog from "../ui/ExplainDialog";
import AvailabilityStatus from "../ui/AvailabilityStatus";
import PharmacyOffers from "./PharmacyOffers";
import AlternativesNotes from "./AlternativesNotes";
import PriceSources from "./PriceSources";
import DataNotes from "./DataNotes";
import BuyGenericButton from "../BuyGenericButton";
import { BUY_GENERIC_NOTE, rowBuyGeneric } from "../../utils/buyGeneric";
import { EmptyState, ErrorState } from "../ui/States";

/** Placeholder with the table's shape, shown while the analysis loads. */
export function MedicineTableSkeleton({ rows = 3 }) {
  return (
    <div className="pa-skel" aria-busy="true" aria-label="Loading medicines">
      {Array.from({ length: rows }).map((_, i) => <div className="skeleton" key={i} />)}
    </div>
  );
}

const RELEASE_NAMES = { sr: "sustained release", er: "extended release", cr: "controlled release", pr: "prolonged release" };

function describeCandidate(c) {
  return [
    c.composition,
    [c.strength, c.form, c.release_type ? RELEASE_NAMES[c.release_type] || "modified release" : null].filter(Boolean).join(" · "),
    c.manufacturer,
  ].filter(Boolean);
}

function decisionSentence(decision) {
  if (!decision) return null;
  const when = decision.decided_at ? new Date(decision.decided_at).toLocaleString() : "an earlier visit";
  if (decision.decision === "unmatched") return `On ${when} you marked this line as not identified.`;
  if (decision.decision === "added_manually") return `On ${when} you added ${decision.medicine_name || "this medicine"} by hand.`;
  return `On ${when} you confirmed ${decision.medicine_name || "a product"}${decision.warnings_acknowledged ? ", after being shown differences from the prescription line" : ""}.`;
}

// One short phrase under the status: why the line is unsettled, so it is visible without opening anything.
function shortReason(row) {
  if (row.userUnmatched) return null;
  if (row.needsDisambiguation) return "Several products fit - choose one";
  if (row.closestGuesses.length > 0) return "Only look-alike products found";
  return "No similar product on file";
}

export function Detail({ row, editable, saving, busy, onUseOption, onReviewGuess, onConfirm, onEdit, onRemove, onExplain, onMarkUnmatched }) {
  const med = row.doctorMedicine;
  const guess = row.guessedMedicine;
  const confirmed = row.status === "user_confirmed";
  // every decision the person made on this line, oldest first (the latest alone for a response that carries no history)
  const decisions = row.verificationHistory.length > 0 ? row.verificationHistory : row.verificationDecision ? [row.verificationDecision] : [];
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
              <div><dt>Dosing (as written)</dt><dd>{dosingSentence(row.instructions) || "Not written"}</dd></div>
              <div><dt>Form</dt><dd>{row.form || "Not on file"}</dd></div>
              <div><dt>Release</dt><dd>{row.releaseLabel ? row.releaseLabel[0].toUpperCase() + row.releaseLabel.slice(1) : "Conventional (not modified-release)"}</dd></div>
              <div><dt>Manufacturer</dt><dd>{med.manufacturer || "Not on file"}</dd></div>
              <div><dt>Pack</dt><dd>{med.pack_size || "Not on file"}</dd></div>
              <div><dt>Availability</dt><dd><AvailabilityStatus medicine={med} discontinued={med.is_discontinued} offers={row.offers} compact /></dd></div>
            </dl>
          ) : (
            <p className="small muted">{row.userEntered
              ? `You entered ${row.userEntered.name} yourself. It is not matched to the dataset, so there are no medicine details, price, savings or safety check for it.${editable ? " Use Review again to change it." : ""}`
              : row.suggested
              ? `Suggested: ${row.suggestion.medicine_name}. The name matches what was read, but nothing is confirmed, so no details, price or safety check are shown.${editable ? " Use Verify to confirm it or enter the details yourself." : ""}`
              : row.userUnmatched
              ? `You marked this line as not identified, so there are no medicine details.${editable ? " Use Review again if you change your mind." : ""}`
              : row.needsDisambiguation
                ? `We did not pick a product for this line: more than one fits.${editable ? " Choose one under \"Possible products\", or use Verify to search." : ""}`
                : `This line is not confirmed, so no medicine details are shown.${editable ? " Review the look-alikes, or use Verify to search for the right medicine." : ""}`}</p>
          )}
          {med && <DataNotes notes={row.dataNotes} />}
          <p className="tiny subtle buy-generic-explained">{BUY_GENERIC_NOTE}</p>
          {med && row.brandUnspecified && (
            <p className="tiny subtle">The prescription names the ingredients but no brand, so any brand with this composition fits. The product shown is one example.</p>
          )}
        </section>

        <section>
          <h4 className="detail-h">{med ? (confirmed ? "Your decision" : "Why we matched it") : "Why this needs verification"}</h4>
          <p className="small">{row.whyReason}</p>
          <p className="tiny subtle">Read from your prescription as <code>{row.rawText}</code>{row.ocrLineConfidence != null && !med && ` (text read with ${Math.round(row.ocrLineConfidence * 100)}% confidence)`}</p>
          {row.confidence != null && <p className="tiny subtle">{CONFIDENCE_EXPLANATION}</p>}
          {!med && dosingSentence(row.instructions) && <p className="tiny subtle">Dosing read from this line: {dosingSentence(row.instructions)}</p>}
          {!med && !row.closestGuesses.length && guess && <p className="tiny subtle">Closest guess: {guess.medicine_name} (not confirmed).</p>}
          {!med && row.closestGuesses.length > 0 && (
            <div className="close-matches">
              <h5>Closest look-alikes (not confirmed)</h5>
              <ul>
                {row.closestGuesses.map((g) => (
                  <li key={g.medicine_id}>
                    <span>
                      <strong>{g.medicine_name}</strong>
                      {describeCandidate(g).map((line) => <small key={line}>{line}</small>)}
                      <small>Similarity {Math.round((g.score || 0) * 100)}%</small>
                    </span>
                    {editable && <button type="button" className="btn btn-secondary btn-sm" disabled={saving} onClick={() => onReviewGuess(g)}>Review this</button>}
                  </li>
                ))}
              </ul>
            </div>
          )}
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
                <div><dt>Reference price</dt><dd>{rupees(row.prescribedPrice)}<span className="sub">{row.priceBasis ? row.priceBasis.label : "Reference price from a dataset snapshot. Not a live price."}</span></dd></div>
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
                        <small>{[alt.manufacturer, alt.pack_size, alt.price_per_unit != null ? `${rupees(alt.price_per_unit)} per unit` : null, !alt.same_pack_quantity ? "different pack size" : null].filter(Boolean).join(" · ")}</small>
                        {alt.price_flag_note && <small className="warn-text">{alt.price_flag_note}</small>}
                      </span>
                      <span className="alt-price"><b>{rupees(alt.price)}</b>{alt.counts_for_savings && alt.savings_percent > 0 && <em>{alt.savings_percent.toFixed(0)}% less</em>}</span>
                    </li>
                  ))}
                </ul>
              ) : <p className="small muted">No comparable alternatives on file.</p>}
              {row.allAlternatives.length > 0 && !row.topAlternative && <p className="tiny subtle">None of these is counted as a saving: each is in a different pack size, has a price that needs checking, or is not cheaper.</p>}
              {row.recommendations[0]?.reason && <p className="tiny subtle">{row.recommendations[0].reason}</p>}
              <AlternativesNotes notes={row.alternativesNotes} />
            </>
          ) : (
            <p className="small muted">{med ? "No reliable reference price is on file for this medicine, so we do not estimate savings." : "Prices appear once the medicine is identified."}</p>
          )}
          {med && (
            <>
              <h5 className="detail-h" style={{ marginTop: "0.9rem" }}>At pharmacies (as reported)</h5>
              <PharmacyOffers offers={row.offers} />
            </>
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

      {confirmed && (
        <p className="tiny subtle">You chose this product. PharmaCompare has not verified that it is the one written on the prescription, or that it is medically equivalent.</p>
      )}
      {row.confirmedWithConflicts && (
        <div className="alert alert-warn" role="note">
          <div>
            <strong>This product differs from the prescription line</strong>
            <ul className="bullets" style={{ margin: "0.3rem 0 0" }}>{row.confirmationConflicts.map((c) => <li key={c}>{c}</li>)}</ul>
            <p className="tiny" style={{ margin: "0.4rem 0 0" }}>Your decision stands, but no saving is counted for this line, because the price comparison describes the product you chose, which may not be the medicine prescribed.</p>
          </div>
        </div>
      )}
      {decisions.length > 0 && (
        <div className="tiny subtle">
          <strong>Decision history</strong>
          <ul className="bullets" style={{ margin: "0.2rem 0 0" }}>
            {decisions.map((d, i) => <li key={`${d.decided_at}-${i}`}>{decisionSentence(d)}</li>)}
          </ul>
          <p style={{ margin: "0.3rem 0 0" }}>Your original line is kept as read: <code>{row.rawText}</code>.</p>
        </div>
      )}

      <div className="detail-actions">
        {editable && !med && <button type="button" className="btn btn-primary btn-sm" onClick={onEdit} disabled={saving || busy}>{row.userUnmatched ? "Review again" : "Verify"}</button>}
        {editable && !med && !row.userUnmatched && <button type="button" className="btn btn-secondary btn-sm" onClick={onMarkUnmatched} disabled={saving || busy}>None of these - mark as not identified</button>}
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
  const [pickerSelection, setPickerSelection] = useState(null);   // a look-alike the person chose to review (still unconfirmed)
  const [conflict, setConflict] = useState(null);                 // differences the backend wants acknowledged before saving
  const [explaining, setExplaining] = useState(null);
  const [saving, setSaving] = useState(false);
  const [removingId, setRemovingId] = useState(null);
  const [actionError, setActionError] = useState("");
  const [entryRow, setEntryRow] = useState(null);                   // the line whose medicine the person is typing in
  const [entryError, setEntryError] = useState("");

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

  // Saving is explicit and two-step when the choice conflicts with the prescription line: the first attempt is
  // refused (409) with the differences, and only a deliberate "Confirm anyway" repeats it with `acknowledge`.
  async function confirmMedicine(medicine, targetRow = pickerRow, acknowledge = false) {
    setSaving(true);
    setActionError("");
    try {
      if (targetRow === "new") await addMedicineManually(prescriptionId, medicine.medicine_id);
      else await correctDetectedMedicine(prescriptionId, targetRow.id, medicine.medicine_id, acknowledge);
      setPickerRow(null);
      setPickerSelection(null);
      setConflict(null);
      await onCorrected();
    } catch (err) {
      if (err?.response?.status === 409 && Array.isArray(err.response.data?.warnings)) {
        setConflict({ row: targetRow, medicine, warnings: err.response.data.warnings });
      } else {
        setConflict(null);
        setActionError(getErrorMessage(err));
      }
    } finally {
      setSaving(false);
    }
  }

  async function saveDetails(row, details) {
    setSaving(true);
    setActionError("");
    setEntryError("");
    try {
      await enterMedicineDetails(prescriptionId, row.id, details);
      setEntryRow(null);
      setPickerRow(null);
      await onCorrected();
    } catch (err) {
      setEntryError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function markUnmatched(row) {
    setSaving(true);
    setActionError("");
    try {
      await markMedicineUnmatched(prescriptionId, row.id);
      setPickerRow(null);
      setPickerSelection(null);
      setConflict(null);
      await onCorrected();
    } catch (err) {
      setActionError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  function openPicker(row, selection = null) {
    setActionError("");
    setPickerSelection(selection);
    setPickerRow(row);
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

  // Verify opens with what we already have for the line: the several close matches if there were any,
  // otherwise the look-alikes the matcher found - listed as suggestions, never as confirmed.
  const pickerLine = pickerRow && pickerRow !== "new" ? pickerRow : null;
  const pickerSuggestions = pickerLine
    ? (pickerLine.needsDisambiguation ? pickerLine.matchOptions : pickerLine.closestGuesses) || []
    : [];
  const picker = (
    <>
      <MedicinePickerDialog
        open={!!pickerRow}
        rawText={pickerRow === "new" ? null : pickerRow?.rawText}
        currentName={pickerRow === "new" ? null : pickerRow?.doctorMedicine?.medicine_name}
        suggestions={pickerSuggestions}
        reasons={pickerLine && !pickerLine.doctorMedicine ? pickerLine.verificationReasons : []}
        initialSelection={pickerSelection}
        saving={saving}
        onCancel={() => { setPickerRow(null); setPickerSelection(null); setConflict(null); }}
        onConfirm={confirmMedicine}
        onMarkUnmatched={pickerLine && !pickerLine.userUnmatched ? () => markUnmatched(pickerLine) : undefined}
        onEnterDetails={pickerLine && !pickerLine.doctorMedicine ? () => { setEntryError(""); setEntryRow(pickerLine); setPickerRow(null); } : undefined}
      />
      {entryRow && (
        <EnterDetailsDialog
          key={entryRow.id}
          open
          rawText={entryRow.rawText}
          initial={initialDetails(entryRow)}
          saving={saving}
          error={entryError}
          onCancel={() => { setEntryRow(null); setEntryError(""); }}
          onSave={(details) => saveDetails(entryRow, details)}
        />
      )}
      <ConfirmWarningsDialog
        open={!!conflict}
        rawText={conflict?.row?.rawText}
        medicineName={conflict?.medicine?.medicine_name}
        warnings={conflict?.warnings || []}
        saving={saving}
        onBack={() => setConflict(null)}
        onConfirmAnyway={() => confirmMedicine(conflict.medicine, conflict.row, true)}
      />
    </>
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
                    <strong>{med ? med.medicine_name : row.userEntered ? row.userEntered.name : row.rawText}</strong>
                    <BuyGenericButton verdict={rowBuyGeneric(row)} onVerify={editable ? () => openPicker(row) : undefined} />
                    <span className="sub">{med ? (row.rawText && row.rawText !== med.medicine_name ? `(${row.rawText})` : "") : (row.userEntered ? `(Read as “${row.rawText}”. Entered by you)` : row.userUnmatched ? "(Marked by you as not identified)" : row.suggested ? `Suggested: ${row.suggestion.medicine_name}, not confirmed` : row.needsDisambiguation ? "(Choose which product)" : row.closestGuesses.length > 0 ? `Closest look-alike, not confirmed: ${row.closestGuesses[0].medicine_name}` : "(Could not be identified)")}</span>
                    {med && row.brandUnspecified && <span className="sub">Generic name - any brand</span>}
                  </td>

                  <td data-label="Strength / Form">
                    <div className="val">{med ? (<><span>{row.strength || "Unknown"}</span><span className="sub">{row.form || ""}</span>{row.releaseLabel && <span className="sub">{row.releaseLabel}</span>}</>) : <span className="muted">{row.userEntered ? [row.strength, row.form].filter(Boolean).join(" · ") || "Entered by you" : row.userUnmatched ? "Not identified" : "Needs confirmation"}</span>}</div>
                  </td>

                  <td data-label="Match status">
                    <div className="val">
                      <span className={`pa-pill is-${status.tone}`}>{status.text}</span>
                      <span className="sub">{confidenceText(row)}</span>
                      {!med && shortReason(row) && <span className="sub">{shortReason(row)}</span>}
                      {!row.userEntered && (row.ocrUncertain || (!med && row.verificationReasons.some((r) => r.includes("low confidence")))) && <span className="sub">Text read with low confidence</span>}
                      {row.formConflict && <span className="sub">Form differs from the prescription</span>}
                      {row.readAssumption && <span className="sub" title={row.readAssumption}>Number read as a dose schedule</span>}
                      {row.confirmedWithConflicts && <span className="sub">Differs from the prescription line</span>}
                      {row.allergyAlert && <span className="pa-pill is-risk" title={row.allergyAlertText || "Allergy alert"}>Allergy alert</span>}
                    </div>
                  </td>

                  <td data-label="Reference price">
                    <div className="val">{priced ? (<>{row.topAlternative ? <s>{rupees(row.prescribedPrice)}</s> : rupees(row.prescribedPrice)}{row.priceNote && <span className="sub" title={row.priceNote}>Unusual price</span>}</>) : <span className="muted">{med && row.brandUnspecified ? "Brand not named" : med ? "Not available" : row.userUnmatched ? "Not identified" : "Identify the medicine first"}</span>}</div>
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
                      <span className="pa-save is-none">{priced ? "No comparable saving" : (med && row.brandUnspecified ? "Brand not named" : med ? "Price not available" : row.userUnmatched ? "Not identified" : "Identify the medicine first")}</span>
                    )}
                  </td>

                  <td className="col-action" data-label="Action">
                    {editable && !med && (
                      <button type="button" className="btn btn-primary btn-sm" onClick={() => openPicker(row)} disabled={busy || saving}>
                        {row.userUnmatched ? "Review again" : "Verify"}
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
                        onUseOption={(opt) => confirmMedicine({ medicine_id: opt.medicine_id, medicine_name: opt.medicine_name }, row)}
                        onReviewGuess={(guess) => openPicker(row, guess)}
                        onConfirm={() => confirmMedicine({ medicine_id: med.medicine_id, medicine_name: med.medicine_name }, row)}
                        onMarkUnmatched={() => markUnmatched(row)}
                        onEdit={() => openPicker(row)}
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
        <PriceSources basis={detail?.price_basis} live={detail?.live_data} />
        {canEdit && <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setActionError(""); setPickerRow("new"); }}>Add a medicine</button>}
      </div>

      {explaining && <ExplainDialog medicine={explaining} onClose={() => setExplaining(null)} />}
      {picker}
    </div>
  );
}
