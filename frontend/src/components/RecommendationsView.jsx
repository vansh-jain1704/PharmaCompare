import { Sparkles } from "lucide-react";
import { groupRecommendations } from "../utils/medicineDisplay";

const CONFIDENCE_LABELS = [
  { min: 0.9, label: "Strong match", className: "badge-success" },
  { min: 0.5, label: "Possible option", className: "badge-warning" },
  { min: 0, label: "Weak signal", className: "badge-muted" },
];

function confidenceMeta(score) {
  return CONFIDENCE_LABELS.find((c) => score >= c.min) || CONFIDENCE_LABELS[CONFIDENCE_LABELS.length - 1];
}

/**
 * Shows Generic/Alternative Recommendation's output: up to a few cheaper,
 * same-composition options per prescribed medicine. Deliberately never
 * singles out a "best" pick - each option is listed with its own
 * confidence and reasoning, and every reason already ends with "confirm
 * with your doctor or pharmacist" from the backend.
 */
export default function RecommendationsView({ recommendations, priceComparisonItems }) {
  const groups = groupRecommendations(recommendations, priceComparisonItems);
  if (groups.length === 0) return null;

  return (
    <div className="recommendations">
      <div className="clinical-findings-header">
        <Sparkles size={18} />
        <h3>Alternatives worth asking about</h3>
      </div>

      {groups.map((group) => (
        <div className="recommendation-group" key={group.pm_id}>
          {group.prescribedName && <p className="recommendation-group-title">For {group.prescribedName}</p>}
          <ul className="recommendation-list">
            {group.recommendations.map((rec, i) => {
              const meta = confidenceMeta(rec.confidence_score ?? 0);
              return (
                <li key={i} className="recommendation-item">
                  <div className="recommendation-header">
                    <strong>{rec.generic_name}</strong>
                    <span className={`badge ${meta.className}`}>{meta.label}</span>
                  </div>
                  <p className="recommendation-reason">{rec.reason}</p>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
