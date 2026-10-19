/**
 * Where a product's own data is missing or does not fit together, as the server found it (data_validation_service). A note is a reason to
 * check against the pack, not a correction, and the absence of notes is not a verification: the data comes from a community dataset.
 */
export default function DataNotes({ notes }) {
  if (!Array.isArray(notes) || notes.length === 0) return null;
  return (
    <div className="data-notes" role="note">
      <p className="tiny" style={{ margin: "0 0 0.2rem" }}><strong>Data notes</strong> (a reason to check the pack, not a correction)</p>
      <ul className="bullets" style={{ margin: 0 }}>
        {notes.map((n) => (
          <li key={n.code} className={n.level === "warn" ? "small warn-text" : "small muted"}>{n.text}</li>
        ))}
      </ul>
    </div>
  );
}
