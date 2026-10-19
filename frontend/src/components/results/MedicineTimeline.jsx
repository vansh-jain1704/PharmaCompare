/**
 * The Medicine Timeline: when each identified medicine is taken, exactly as the prescription wrote it.
 *
 * Built by the backend (timeline_service) from the instructions it read, and rendered here as given, so this screen and
 * the PDF cannot disagree. Nothing is defaulted: a missing duration says "not written", a schedule that was only partly
 * readable says "possible", and a line that is not identified is listed apart instead of being named.
 */
function Item({ item }) {
  return (
    <li>
      <strong>{item.medicine}</strong>
      <span className="tl-detail">
        {[item.frequency, item.amount, item.timing].filter(Boolean).join(" · ") || "amount not written"}
      </span>
      <span className="tl-detail">{item.duration}</span>
      {item.possible && <span className="tag tag-warning" title="The digits were read as a schedule but may be a strength or a misread">Possible schedule {item.schedule}</span>}
    </li>
  );
}

export default function MedicineTimeline({ timeline }) {
  if (!timeline || !timeline.has_content) {
    return (
      <p className="small muted">
        No dosing instructions (times of day, how long) could be read from this prescription. Nothing is assumed: check the
        original prescription.
      </p>
    );
  }
  return (
    <div className="tl">
      {(timeline.slots.length > 0 || timeline.groups.length > 0) && (
        <div className="tl-grid">
          {timeline.slots.map((slot) => (
            <section key={slot.slot} className="tl-card" aria-label={slot.label}>
              <h3>{slot.label}</h3>
              <ul>{slot.items.map((item) => <Item key={`${slot.slot}-${item.pm_id}`} item={item} />)}</ul>
            </section>
          ))}
          {timeline.groups.map((group) => (
            <section key={group.group} className="tl-card is-group" aria-label={group.label}>
              <h3>{group.label}</h3>
              <ul>{group.items.map((item) => <Item key={`${group.group}-${item.pm_id}`} item={item} />)}</ul>
            </section>
          ))}
        </div>
      )}

      {timeline.not_identified.length > 0 && (
        <div className="alert alert-warn" role="note">
          <div>
            <strong>Not in the timeline until identified</strong>
            <ul className="bullets" style={{ margin: "0.3rem 0 0" }}>
              {timeline.not_identified.map((n) => (
                <li key={n.pm_id}>
                  <code>{n.source_text}</code>: {n.read_as ? `read as ${n.read_as}` : "no schedule read"}, {n.duration}
                  {n.possible ? " (only possibly a schedule)" : ""}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <p className="tiny subtle">
        Taken from the instructions written on the prescription. A schedule marked possible was only partly readable: check the
        original. Nothing here is a dosing recommendation.
      </p>
    </div>
  );
}
