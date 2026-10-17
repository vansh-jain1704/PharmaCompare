/** A plain collapsible row (native <details>): a title, an optional short note, and content that opens below. */
export default function Disclosure({ id, title, note, children }) {
  return (
    <details className="pa-disc" id={id}>
      <summary>
        <span className="pa-disc-title">{title}</span>
        {note && <span className="pa-disc-note">{note}</span>}
      </summary>
      <div className="pa-disc-body">{children}</div>
    </details>
  );
}
