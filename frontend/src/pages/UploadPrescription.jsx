import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Check, CheckCircle2, FileText, Lightbulb, RotateCcw, ScanSearch, UploadCloud, X } from "lucide-react";
import { uploadPrescription } from "../api/prescriptionApi";
import { getErrorMessage } from "../api/getErrorMessage";
import Page from "../components/Page";
import { ErrorState } from "../components/ui/States";

const ALLOWED_EXTENSIONS = ["png", "jpg", "jpeg", "pdf"];
const MAX_SIZE_MB = 10;
const MAX_NAME_LENGTH = 255;

// The backend does all of this in a single request, so the client cannot see
// which stage it is really on. The journey advances on a timer while the
// request is in flight (stopping at "Safety") and jumps to "Report ready"
// only when the response actually arrives.
const STAGES = [
  { label: "Uploading", note: "Sending your file securely" },
  { label: "Reading", note: "OCR reads every line" },
  { label: "Matching", note: "Finding each medicine" },
  { label: "Safety", note: "Checking interactions" },
  { label: "Report ready", note: "Your analysis is done" },
];
const STAGE_MS = 2600;

const TIPS = [
  "Lay the page flat in good light, with all four corners in the frame.",
  "Make sure the medicine names are in focus and not cut off.",
  "A photo or a PDF works. Multi-page PDFs are read page by page.",
];

const extensionOf = (name) => name.split(".").pop().toLowerCase();

function formatSize(bytes) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function Journey({ stage }) {
  return (
    <ol className="stepper" aria-label="Processing journey">
      {STAGES.map(({ label, note }, i) => {
        const state = i < stage ? "is-done" : i === stage ? "is-active" : "";
        return (
          <li key={label} className={`stepper-step ${state}`} aria-current={i === stage ? "step" : undefined}>
            <span className="stepper-dot">{i < stage ? <Check size={15} strokeWidth={3} /> : i + 1}</span>
            <span className="stepper-label">{label}</span>
            <span className="stepper-note">{note}</span>
          </li>
        );
      })}
    </ol>
  );
}

export default function UploadPrescription() {
  const fileInputRef = useRef(null);

  const [selectedFile, setSelectedFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [prescriptionName, setPrescriptionName] = useState("");
  const [fieldError, setFieldError] = useState("");
  const [serverError, setServerError] = useState("");
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [stage, setStage] = useState(0);

  // Preview for images; released when the file changes or the page closes.
  useEffect(() => {
    if (!selectedFile || extensionOf(selectedFile.name) === "pdf") { setPreviewUrl(null); return undefined; }
    const url = URL.createObjectURL(selectedFile);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [selectedFile]);

  useEffect(() => {
    if (!submitting) return undefined;
    setStage(0);
    const id = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 2)), STAGE_MS);
    return () => clearInterval(id);
  }, [submitting]);

  function acceptFile(file) {
    setResult(null);
    setServerError("");
    setFieldError("");
    if (!file) { setSelectedFile(null); return; }
    if (!ALLOWED_EXTENSIONS.includes(extensionOf(file.name))) {
      setFieldError("That file type is not supported. Please use a JPG, PNG or PDF.");
      setSelectedFile(null);
      return;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      setFieldError(`That file is too large. The limit is ${MAX_SIZE_MB} MB.`);
      setSelectedFile(null);
      return;
    }
    setSelectedFile(file);
  }

  function clearFile() {
    setSelectedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleSubmit(e) {
    e?.preventDefault();
    if (!selectedFile) {
      setFieldError("Please choose a prescription image or PDF first.");
      return;
    }
    setSubmitting(true);
    setServerError("");
    setResult(null);
    try {
      const res = await uploadPrescription(selectedFile, prescriptionName.trim());
      setStage(STAGES.length - 1);
      setResult({ ok: true, ...res.data });
    } catch (err) {
      if (err.response?.status === 422) {
        // "unclear image" - a normal outcome, not a system failure
        setResult({ ok: false, ...err.response.data });
      } else {
        setServerError(getErrorMessage(err));
      }
    } finally {
      setSubmitting(false);
    }
  }

  function resetForm() {
    clearFile();
    setPrescriptionName("");
    setResult(null);
    setServerError("");
    setFieldError("");
  }

  const showForm = !submitting && !result?.ok && !result;

  return (
    <Page
      crumbs={[{ label: "Dashboard", to: "/dashboard" }, { label: "Analyze prescription" }]}
      eyebrow="New analysis"
      title="Analyze a prescription"
      subtitle="We will read it, match each medicine, compare prices and check safety."
    >
      <div className="upload-layout">
        <div className="upload-main">
          {showForm && (
            <form className="rise" onSubmit={handleSubmit} noValidate>
              <div
                className={`dropzone ${dragging ? "is-dragging" : ""} ${selectedFile ? "has-file" : ""}`}
                role="button" tabIndex={0} aria-label="Choose or drop a prescription file"
                onClick={() => !selectedFile && fileInputRef.current?.click()}
                onKeyDown={(e) => { if (!selectedFile && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); fileInputRef.current?.click(); } }}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => { e.preventDefault(); setDragging(false); acceptFile(e.dataTransfer.files?.[0]); }}
              >
                <input ref={fileInputRef} type="file" accept=".png,.jpg,.jpeg,.pdf" hidden onChange={(e) => acceptFile(e.target.files?.[0])} />
                {selectedFile ? (
                  <div className="preview">
                    <div className="preview-thumb">
                      {previewUrl
                        ? <img src={previewUrl} alt="Prescription preview" />
                        : <span className="preview-pdf"><FileText size={34} />PDF</span>}
                    </div>
                    <div className="preview-meta">
                      <strong>{selectedFile.name}</strong>
                      <span>{formatSize(selectedFile.size)} · ready to analyze</span>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={clearFile}><X size={14} /> Choose a different file</button>
                    </div>
                  </div>
                ) : (
                  <>
                    <span className="dz-icon"><UploadCloud size={30} /></span>
                    <p className="dz-title">Drag &amp; drop your prescription</p>
                    <p className="dz-hint">or <span className="dz-link">browse files</span> · JPG, PNG or PDF · up to {MAX_SIZE_MB} MB</p>
                  </>
                )}
              </div>

              {fieldError && <p className="field-error" role="alert" style={{ marginTop: "var(--s-3)" }}>{fieldError}</p>}

              <div className="field" style={{ marginTop: "var(--s-5)" }}>
                <label htmlFor="prescriptionName">Prescription name <span className="subtle">(optional)</span></label>
                <input
                  id="prescriptionName" type="text" placeholder="e.g. Dr. Sharma visit"
                  value={prescriptionName} onChange={(e) => setPrescriptionName(e.target.value)} maxLength={MAX_NAME_LENGTH}
                />
              </div>

              <button type="submit" className="btn btn-primary btn-lg btn-block" disabled={!selectedFile}>
                <ScanSearch size={18} /> Analyze Prescription
              </button>
            </form>
          )}

          {submitting && (
            <section className="process rise" aria-live="polite">
              <h2>Analyzing your prescription…</h2>
              <p className="small muted">This can take up to 20 seconds the first time.</p>
              <Journey stage={stage} />
            </section>
          )}

          {serverError && !submitting && (
            <section className="process rise">
              <ErrorState
                title="We could not process that upload."
                message={serverError}
                action={<button type="button" className="btn btn-primary btn-sm" onClick={handleSubmit}><RotateCcw size={14} /> Try again</button>}
              />
            </section>
          )}

          {result?.ok && (
            <section className="process rise">
              <Journey stage={STAGES.length} />
              <div className="done-block">
                <span className="state-icon is-ok"><CheckCircle2 size={28} /></span>
                <h2>Your analysis is ready</h2>
                <p className="small muted">{result.prescription_name || selectedFile?.name}</p>
                <div className="row" style={{ flexWrap: "wrap", justifyContent: "center" }}>
                  <Link to={`/prescriptions/${result.prescription_id}`} className="btn btn-primary btn-lg">View Analysis</Link>
                  <button type="button" className="btn btn-ghost" onClick={resetForm}>Analyze another</button>
                </div>
              </div>
            </section>
          )}

          {result && !result.ok && (
            <section className="process rise">
              <div className="alert alert-warn">
                {result.message || "This image is too unclear to read reliably. Please retake the photo with better lighting and focus, then try again."}
              </div>
              <button type="button" className="btn btn-secondary" onClick={resetForm}>Try again</button>
            </section>
          )}
        </div>

        <aside className="upload-aside rise d2" aria-label="Tips for a good scan">
          <h2><Lightbulb size={17} /> For the best result</h2>
          <ul>{TIPS.map((t) => <li key={t}>{t}</li>)}</ul>
          <p className="tiny subtle">Your file is stored privately against your account. Messy handwriting may not be read correctly, so we always show a confirmation step when unsure.</p>
        </aside>
      </div>
    </Page>
  );
}
