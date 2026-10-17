import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, FileText, FileUp, RotateCcw, Trash2 } from "lucide-react";
import { listPrescriptions, deletePrescription } from "../api/prescriptionApi";
import { getErrorMessage } from "../api/getErrorMessage";
import ConfirmDialog from "../components/ConfirmDialog";
import Page from "../components/Page";
import { EmptyState, ErrorState } from "../components/ui/States";
import usePrescriptionSummaries, { invalidateSummary } from "../hooks/usePrescriptionSummaries";
import { prescriptionTitle, rupees } from "../utils/format";

const NOT_READY = {
  needs_reupload: "Needs re-upload",
  processing_failed: "Processing failed",
  uploaded: "Not processed",
};

const monthKey = (d) => d.toLocaleDateString("en-GB", { month: "long", year: "numeric" });

export default function PrescriptionHistory() {
  const [prescriptions, setPrescriptions] = useState([]);
  const [state, setState] = useState("loading"); // loading | ready | error
  const [error, setError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  function load() {
    setState("loading");
    listPrescriptions()
      .then((res) => { setPrescriptions(res.data.prescriptions); setState("ready"); })
      .catch((err) => { setError(getErrorMessage(err)); setState("error"); });
  }
  useEffect(load, []);

  const { summaries } = usePrescriptionSummaries(prescriptions);

  const groups = useMemo(() => {
    const out = [];
    prescriptions.forEach((p) => {
      const key = monthKey(new Date(p.upload_date));
      const last = out[out.length - 1];
      if (last && last.key === key) last.items.push(p);
      else out.push({ key, items: [p] });
    });
    return out;
  }, [prescriptions]);

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await deletePrescription(deleteTarget.prescription_id);
      invalidateSummary(deleteTarget.prescription_id);
      setPrescriptions((prev) => prev.filter((p) => p.prescription_id !== deleteTarget.prescription_id));
      setDeleteTarget(null);
    } catch (err) {
      setDeleteError(getErrorMessage(err));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <Page
      crumbs={[{ label: "Dashboard", to: "/dashboard" }, { label: "History" }]}
      title="History"
      subtitle="Every prescription you have analyzed."
      actions={<Link to="/upload" className="btn btn-primary btn-sm"><FileUp size={15} /> Analyze new</Link>}
    >
      {state === "loading" && <div className="stack">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 78 }} />)}</div>}

      {state === "error" && (
        <section className="panel">
          <ErrorState
            title="We could not load your history." message={error}
            action={<button type="button" className="btn btn-primary btn-sm" onClick={load}><RotateCcw size={14} /> Try again</button>}
          />
        </section>
      )}

      {state === "ready" && prescriptions.length === 0 && (
        <section className="panel">
          <EmptyState
            icon={<FileText size={26} />} title="No analyses yet" message="Analyze a prescription and it will appear here with its savings."
            action={<Link to="/upload" className="btn btn-primary btn-sm"><FileUp size={14} /> Analyze a prescription</Link>}
          />
        </section>
      )}

      {deleteError && <div className="alert alert-risk" role="alert">{deleteError}</div>}

      {state === "ready" && groups.map((group) => (
        <section className="history-group rise" key={group.key} aria-label={group.key}>
          <h2 className="history-month">{group.key}</h2>
          <ul className="history-list">
            {group.items.map((p) => {
              const s = summaries[p.prescription_id];
              const notReady = NOT_READY[p.status];
              const detail = s
                ? `${s.detected} medicine${s.detected === 1 ? "" : "s"}${s.savings > 0 ? ` • ${rupees(s.savings)} potential savings` : ""}`
                : null;
              return (
                <li key={p.prescription_id} className="history-item">
                  <span className="history-dot" aria-hidden="true" />
                  <div className="history-card">
                    <div className="history-main">
                      <strong>{prescriptionTitle(p)}</strong>
                      {notReady
                        ? <span className="pill tone-risk">{notReady}</span>
                        : detail ? <span className="history-detail">{detail}</span> : <span className="skeleton inline-skel" aria-hidden="true" />}
                      {s && s.needsVerification > 0 && <span className="pill tone-warn">{s.needsVerification} to verify</span>}
                    </div>
                    <div className="history-actions">
                      {!notReady && <Link to={`/prescriptions/${p.prescription_id}`} className="btn btn-soft btn-sm">View Analysis <ArrowRight size={14} /></Link>}
                      <button type="button" className="icon-btn" aria-label="Delete this prescription" title="Delete" onClick={() => setDeleteTarget(p)}><Trash2 size={16} /></button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ))}

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete this prescription?"
        message={deleteTarget ? `This will permanently delete "${prescriptionTitle(deleteTarget)}" and all of its analysis. This cannot be undone.` : ""}
        confirmLabel="Delete" danger busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => { setDeleteTarget(null); setDeleteError(""); }}
      />
    </Page>
  );
}
