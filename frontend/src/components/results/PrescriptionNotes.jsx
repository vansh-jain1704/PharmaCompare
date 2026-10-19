/**
 * What is on the prescription besides medicines (instructions, Hindi notes), and what the allergy check had to work with. Both are stated
 * as the server worked them out: a missing allergy list never reads as "no allergy found".
 */
export function AllergyNotice({ check }) {
  if (!check) return null;
  return (
    <div className={`alert ${check.declared ? "alert-info" : "alert-warn"}`} role="note">
      <div><strong>Allergy check.</strong> {check.message}</div>
    </div>
  );
}

export default function PrescriptionNotes({ notes }) {
  if (!Array.isArray(notes) || notes.length === 0) return null;
  return (
    <section className="panel" aria-label="Other instructions on the prescription">
      <h2 className="section-label">Other instructions on the prescription (not medicines)</h2>
      <ul className="bullets">
        {notes.map((n) => (
          <li key={n.text}>
            <span lang={n.kind === "hindi_note" ? "hi" : undefined}>{n.text}</span>
            {n.kind === "hindi_note" && (
              <span className="tiny subtle"> Handwritten Hindi note, shown as read.{n.possible_meaning ? ` Automatic reading, please check it: “${n.possible_meaning}”. It does not say which medicine it belongs to.` : " It could not be translated automatically."}</span>
            )}
            {n.uncertain && <span className="tiny subtle"> (read with low confidence)</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
