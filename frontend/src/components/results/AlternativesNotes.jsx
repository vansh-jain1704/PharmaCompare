/**
 * What a price comparison with alternatives does and does not establish, as the server states it (recommendation_notes): what was matched,
 * what is NOT compared, that the prescribed medicine's allergy and interaction checks carry over, and - for a line that is not settled -
 * that the alternatives are for information only. Never a recommendation to switch.
 */
export default function AlternativesNotes({ notes }) {
  if (!notes) return null;
  return (
    <div className="alt-notes">
      {notes.information_only && <div className="alert alert-warn" role="note"><div>{notes.information_only}</div></div>}
      <p className="tiny subtle" style={{ margin: "0.5rem 0 0.2rem" }}><strong>How these were chosen:</strong> products with {notes.matched.join("; ")}.</p>
      <p className="tiny subtle" style={{ margin: "0 0 0.2rem" }}><strong>Not compared:</strong> {notes.not_compared.join("; ")}.</p>
      <p className="tiny subtle" style={{ margin: 0 }}>{notes.safety} {notes.ask_first}</p>
    </div>
  );
}
