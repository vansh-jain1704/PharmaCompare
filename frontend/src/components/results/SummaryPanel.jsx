import { rupees } from "../../utils/format";

/**
 * Savings and match counts for the analysis page. Every number is computed
 * from the same rows the table shows. The savings figure counts only
 * medicines with BOTH a reliable reference price and a real alternative, and
 * says how many that was, so it can never look bigger than its evidence.
 */
export default function SummaryPanel({ summary, totalCount }) {
  const hasSavings = summary.savings > 0;
  const pct = summary.savingsPercent == null ? null : Math.round(summary.savingsPercent);
  // A line the matcher flagged "Check match" is shown in orange in the table, so
  // it is counted with the lines that need attention rather than the settled ones.
  const settled = summary.autoMatched + summary.userConfirmed - summary.needsCheck;
  const attention = summary.needsVerification + summary.needsCheck;

  return (
    <section className="pa-summary" aria-label="Summary">
      <div className="pa-savings">
        <span className="pa-label">Estimated savings</span>
        {hasSavings ? (
          <>
            <div className="pa-amount num">{rupees(summary.savings)}</div>
            {pct != null && <p>{pct}% lower than reference price</p>}
          </>
        ) : (
          <>
            <div className="pa-amount is-none">None found</div>
            <p>No cheaper same-ingredient option with a reliable reference price</p>
          </>
        )}
      </div>

      <dl className="pa-stats">
        <div>
          <dt>Medicines detected</dt>
          <dd className="num">{summary.detected}</dd>
        </div>
        <div>
          <dt>{summary.userConfirmed > 0 ? "Matched or confirmed" : "Automatically matched"}</dt>
          <dd className="num">{settled}</dd>
        </div>
        <div className={attention > 0 ? "is-attn" : ""}>
          <dt>Needs verification</dt>
          <dd className="num">{attention}</dd>
        </div>
      </dl>

      {hasSavings && (
        <p className="pa-summary-note">
          Counted across {summary.savingsCovered} of {totalCount} medicine{totalCount === 1 ? "" : "s"} that have both a reference price and a cheaper
          same-ingredient option.
        </p>
      )}
    </section>
  );
}
