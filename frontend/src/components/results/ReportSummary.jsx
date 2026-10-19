import { useState } from "react";
import { Sparkles } from "lucide-react";
import { getReportSummary } from "../../api/prescriptionApi";
import { getErrorMessage } from "../../api/getErrorMessage";

/** The summary text with who wrote it: Gemini (only after it passed the server's checks) or PharmaCompare. Rendered exactly as given. */
export function SummaryView({ summary }) {
  return (
    <div className="summary-text">
      <p>{summary.text}</p>
      <p className="tiny subtle"><em>{summary.label}</em></p>
    </div>
  );
}

/**
 * A plain-language summary of the analysis, written ON REQUEST (nothing is generated or sent until the button is pressed).
 * Uses Google Gemini when it is set up on the server; otherwise PharmaCompare writes it from the same figures.
 */
export default function ReportSummary({ prescriptionId }) {
  const [state, setState] = useState({ status: "idle" });

  async function write() {
    setState({ status: "loading" });
    try {
      const res = await getReportSummary(prescriptionId);
      setState({ status: "ready", summary: res.data });
    } catch (err) {
      setState({ status: "error", message: getErrorMessage(err) });
    }
  }

  return (
    <div className="report-summary">
      {state.status === "ready" ? <SummaryView summary={state.summary} /> : (
        <>
          <button type="button" className="btn btn-secondary btn-sm" onClick={write} disabled={state.status === "loading"}>
            <Sparkles size={14} /> {state.status === "loading" ? "Writing…" : "Write a plain-language summary"}
          </button>
          <p className="tiny subtle">
            Uses Google Gemini when it is set up on this server, otherwise PharmaCompare writes it from the same figures. Only medicine names,
            strengths, schedules and counts are used: never your name, the photo or the original text.
          </p>
          {state.status === "error" && <div className="alert alert-risk" role="alert">{state.message}</div>}
        </>
      )}
    </div>
  );
}
