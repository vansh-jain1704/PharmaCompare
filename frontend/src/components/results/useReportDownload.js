import { useState } from "react";
import { downloadSmartReport } from "../../api/prescriptionApi";
import { getErrorMessage } from "../../api/getErrorMessage";

/**
 * Downloads the Smart Health Report PDF the backend renders from this
 * prescription's stored results. It is regenerated server-side on every
 * request, so the document can never disagree with what is on screen.
 */
export default function useReportDownload(prescriptionId, label) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function download() {
    setBusy(true);
    setError("");
    try {
      const res = await downloadSmartReport(prescriptionId);
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const safeName = (label || `prescription_${prescriptionId}`).replace(/[^A-Za-z0-9_-]+/g, "_");
      const link = document.createElement("a");
      link.href = url;
      link.download = `PharmaCompare_Report_${safeName}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return { download, busy, error };
}
