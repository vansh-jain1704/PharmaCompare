import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { RotateCcw } from "lucide-react";
import { getPrescription } from "../api/prescriptionApi";
import { getErrorMessage } from "../api/getErrorMessage";
import Page from "../components/Page";
import MedicineTable, { MedicineTableSkeleton } from "../components/results/MedicineTable";
import SummaryPanel from "../components/results/SummaryPanel";
import MedicineTimeline from "../components/results/MedicineTimeline";
import PhotoQualityNotes from "../components/PhotoQualityNotes";
import ReportSummary from "../components/results/ReportSummary";
import StatusLegend from "../components/results/StatusLegend";
import PrescriptionNotes, { AllergyNotice } from "../components/results/PrescriptionNotes";
import Disclosure from "../components/results/Disclosure";
import useReportDownload from "../components/results/useReportDownload";
import ClinicalFindingsView from "../components/ClinicalFindingsView";
import RecommendationsView from "../components/RecommendationsView";
import OcrResultView from "../components/OcrResultView";
import { ErrorState } from "../components/ui/States";
import { DEMO_DISCLAIMER } from "../utils/disclaimers";
import { formatDate, prescriptionTitle } from "../utils/format";
import { normalizePriceComparison } from "../utils/medicineDisplay";
import { summarizeDetail } from "../utils/summary";
import { invalidateSummary } from "../hooks/usePrescriptionSummaries";

const NOT_PROCESSED = {
  needs_reupload: "Needs re-upload",
  processing_failed: "Processing failed",
  uploaded: "Not processed",
};

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

/**
 * "Prescription Analysis": one saved prescription, read from the existing
 * detail endpoint. Top to bottom: title and date, savings and match counts,
 * the medicine table, Safety and Original text (closed until opened), and the
 * Smart Health Report.
 *
 * This page uses a white, blue-accented look. It is applied by a body class
 * for as long as the page is mounted, so no other page is affected.
 */
export default function PrescriptionReport() {
  const { id } = useParams();
  const prescriptionId = Number(id);
  const [state, setState] = useState({ status: "loading" });

  useEffect(() => {
    document.body.classList.add("theme-analysis");
    return () => document.body.classList.remove("theme-analysis");
  }, []);

  const load = useCallback(async ({ quiet = false } = {}) => {
    if (!quiet) setState({ status: "loading" });
    try {
      const res = await getPrescription(prescriptionId);
      invalidateSummary(prescriptionId);
      setState({ status: "ready", detail: res.data });
    } catch (err) {
      // On a quiet refresh keep showing what we had rather than blanking the report.
      if (quiet) throw err;
      setState({ status: "error", message: getErrorMessage(err), notFound: err.response?.status === 404 });
    }
  }, [prescriptionId]);

  useEffect(() => { load(); }, [load]);

  const detail = state.detail;
  const meta = detail?.prescription;
  const summary = useMemo(() => (detail ? summarizeDetail(detail) : null), [detail]);
  const { download, busy: downloading, error: downloadError } = useReportDownload(prescriptionId, prescriptionTitle(meta));
  const ready = state.status === "ready";

  const findings = detail?.clinical_analysis?.findings || [];
  const ocr = detail?.ocr_result;
  const ocrLines = ocr?.line_results || [];
  const ocrConfidence = ocr ? parseFloat(ocr.confidence_score) : null;

  // "Dr Sharma visit · 10 Oct 2026 · 3 medicines analyzed" - the name only when the user gave one.
  const userName = (meta?.prescription_name || "").trim();
  const named = userName && !/\.(png|jpe?g|pdf)$/i.test(userName);
  const metaLine = ready ? [
    named ? userName : null,
    meta?.upload_date ? formatDate(meta.upload_date) : null,
    `${plural(summary.detected, "medicine")} analyzed`,
    NOT_PROCESSED[meta?.status] || null,
  ].filter(Boolean) : [];

  return (
    <Page
      back={{ to: "/prescriptions", label: "Back to History" }}
      title="Prescription Analysis"
      meta={ready && metaLine.map((m) => <span key={m}>{m}</span>)}
      actions={ready && (
        <button type="button" className="btn pa-outline" onClick={download} disabled={downloading}>
          {downloading ? "Preparing…" : "Download Report"}
        </button>
      )}
    >
      {downloadError && <div className="alert alert-risk" role="alert">{downloadError}</div>}

      {state.status === "loading" && <MedicineTableSkeleton />}

      {state.status === "error" && (
        <ErrorState
          title={state.notFound ? "We could not find that analysis." : "Something went wrong while loading this analysis."}
          message={state.notFound ? "It may have been deleted." : state.message}
          action={state.notFound
            ? <Link to="/prescriptions" className="btn btn-primary btn-sm">Go to history</Link>
            : <button type="button" className="btn btn-primary btn-sm" onClick={() => load()}><RotateCcw size={14} /> Try again</button>}
        />
      )}

      {ready && (
        <div className="pa">
          <SummaryPanel summary={summary} totalCount={summary.detected} />
          <p className="pa-notice">{DEMO_DISCLAIMER}</p>
          <PhotoQualityNotes quality={detail.image_quality} showOk />
          <ReportSummary prescriptionId={prescriptionId} />

          <section className="pa-section" aria-labelledby="pa-meds">
            <h2 id="pa-meds">Detected Medicines</h2>
            <p className="pa-sub">Here are the medicines found in your prescription.</p>
            <StatusLegend />
            <MedicineTable detail={detail} prescriptionId={prescriptionId} onCorrected={() => load({ quiet: true })} />
          </section>

          <PrescriptionNotes notes={detail.notes} />
          <AllergyNotice check={detail.allergy_check} />

          <section className="pa-section" aria-labelledby="pa-timeline">
            <h2 id="pa-timeline">Medicine Timeline</h2>
            <p className="pa-sub">When each identified medicine is taken, as the prescription wrote it.</p>
            <MedicineTimeline timeline={detail.timeline} />
          </section>

          <section className="pa-more" aria-label="Supporting detail">
            <Disclosure id="safety" title="Safety & Interactions" note={findings.length ? plural(findings.length, "finding") : "No findings recorded"}>
              {findings.length === 0 && <p className="small muted">No interaction, duplicate or allergy findings were recorded for this prescription. That is not a guarantee of safety, so check with your pharmacist.</p>}
              <ClinicalFindingsView analysis={detail.clinical_analysis} />
              <RecommendationsView recommendations={detail.recommendations} priceComparisonItems={normalizePriceComparison(detail.price_comparison)} />
            </Disclosure>

            <Disclosure id="ocr" title="Original Prescription Text" note={ocrLines.length ? plural(ocrLines.length, "line") : null}>
              {ocrLines.length > 0
                ? <OcrResultView lines={ocrLines} rawText={ocr.extracted_text} confidence={ocrConfidence} />
                : <p className="small muted">No text was recorded for this prescription.</p>}
            </Disclosure>
          </section>

          <section className="pa-report" aria-labelledby="pa-report-h">
            <div>
              <h2 id="pa-report-h">Smart Health Report</h2>
              <p>A one-page PDF of this analysis: the medicines, price comparison, savings and safety findings.</p>
            </div>
            <button type="button" className="btn btn-primary btn-lg" onClick={download} disabled={downloading}>
              {downloading ? "Preparing…" : "Generate Smart Health Report"}
            </button>
          </section>
        </div>
      )}
    </Page>
  );
}
