import { ShieldCheck, AlertTriangle, Info } from "lucide-react";
import { SEVERITY_META, ISSUE_TYPE_LABELS } from "../utils/medicineDisplay";

/**
 * Shows the Clinical Decision Engine's output. Deliberately never phrases
 * anything as a diagnosis or an instruction to stop/start/change a
 * medicine - every finding's own recommendation text (from the backend)
 * already says to verify with a doctor/pharmacist, and this component
 * just displays it as-is.
 */
export default function ClinicalFindingsView({ analysis }) {
  if (!analysis || !analysis.findings || analysis.findings.length === 0) {
    return null;
  }

  const { risk_level, summary, findings } = analysis;
  const riskMeta = SEVERITY_META[risk_level] || { label: risk_level, className: "badge-muted" };

  return (
    <div className="clinical-findings">
      <div className="clinical-findings-header">
        <ShieldCheck size={18} />
        <h3>Safety check</h3>
        <span className={`badge ${riskMeta.className}`}>{riskMeta.label}</span>
      </div>
      {summary && <p className="page-subtitle">{summary}</p>}

      <ul className="findings-list">
        {findings.map((f, i) => {
          const meta = SEVERITY_META[f.severity] || { label: f.severity, className: "badge-muted" };
          const isNotable = f.severity !== "NEEDS_VERIFICATION" && f.issue_type !== "allergy_check";
          return (
            <li key={i} className={`finding-item ${isNotable ? "is-notable" : ""}`}>
              <div className="finding-header">
                {isNotable ? <AlertTriangle size={15} /> : <Info size={15} />}
                <strong>{ISSUE_TYPE_LABELS[f.issue_type] || f.issue_type}</strong>
                <span className={`badge ${meta.className}`}>{meta.label}</span>
              </div>
              {f.medicines_involved?.length > 0 && (
                <p className="finding-medicines">
                  {f.medicines_involved.map((m) => m.medicine_name).join(" + ")}
                </p>
              )}
              <p className="finding-explanation">{f.explanation}</p>
              <p className="finding-recommendation">{f.recommendation}</p>
              <p className="finding-source">Source: {f.data_source}</p>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
