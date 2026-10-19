import { STATUS_MEANINGS } from "../../utils/statusMeanings";

/** The status words and what they mean, shown above the medicines table. */
export default function StatusLegend() {
  return (
    <details className="pa-disc">
      <summary><span className="pa-disc-title">What the status words mean</span></summary>
      <div className="pa-disc-body">
        <ul className="bullets">
          {STATUS_MEANINGS.map((s) => (
            <li key={s.word}><span className={`pa-pill is-${s.tone}`}>{s.word}</span> {s.text}</li>
          ))}
        </ul>
      </div>
    </details>
  );
}
