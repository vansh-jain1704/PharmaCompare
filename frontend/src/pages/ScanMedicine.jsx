import { useRef, useState } from "react";
import { Camera, Factory, Info, RotateCcw } from "lucide-react";
import Page from "../components/Page";
import MedicineDrawer from "../components/MedicineDrawer";
import PhotoQualityNotes from "../components/PhotoQualityNotes";
import ExplainDialog from "../components/ui/ExplainDialog";
import { ErrorState } from "../components/ui/States";
import { scanMedicine } from "../api/prescriptionApi";
import { getErrorMessage } from "../api/getErrorMessage";
import { rupees } from "../utils/format";

/**
 * The result of scanning a pack: possible products for the text read from it, NEVER a confirmation. Rendered as the server sent it, with its
 * notice first and the text that was read, so the person can see what the candidates are based on.
 */
export function ScanResults({ result, onOpen }) {
  return (
    <div className="scan-results">
      <div className="alert alert-warn" role="note">
        <div><Info size={14} aria-hidden="true" /> {result.notice}</div>
      </div>
      <PhotoQualityNotes quality={result.image_quality} />

      {result.candidates.length === 0 ? (
        <p className="small muted">{result.message}</p>
      ) : (
        <div className="med-grid">
          {result.candidates.map((m) => (
            <button type="button" key={m.medicine_id} className="med-card" onClick={() => onOpen(m)} aria-label={`Open details for ${m.medicine_name}`}>
              <span className="med-card-top">
                <strong>{m.medicine_name}</strong>
                {m.settled_by_reader && <span className="tag tag-warning">Best match for the text (not confirmed)</span>}
                {m.is_discontinued && <span className="pill tone-risk">Discontinued</span>}
              </span>
              <span className="med-comp">{m.composition || "Composition not on file"}</span>
              <span className="med-meta">{[m.display_strength || m.strength, m.form, m.release_label].filter(Boolean).join(" · ")}</span>
              <span className="med-maker"><Factory size={12} /> {m.manufacturer || "Maker not on file"}</span>
              <span className="tiny subtle">Offered because of the line: “{m.from_line}”</span>
              {m.reasons?.length > 0 && <span className="tiny subtle">{m.reasons[0]}</span>}
              <span className="med-bottom"><b className="num">{rupees(m.price)}</b><span className="med-more">Details →</span></span>
            </button>
          ))}
        </div>
      )}

      {result.lines?.length > 0 && (
        <details className="pa-disc">
          <summary><span className="pa-disc-title">Text read from the pack</span><span className="pa-disc-note">{result.lines.length} lines</span></summary>
          <div className="pa-disc-body">
            <ul className="bullets">{result.lines.map((l, i) => <li key={`${i}-${l.text}`}><code>{l.text}</code></li>)}</ul>
          </div>
        </details>
      )}
    </div>
  );
}

export default function ScanMedicine() {
  const [state, setState] = useState({ status: "idle" });
  const [selected, setSelected] = useState(null);
  const [explaining, setExplaining] = useState(null);
  const inputRef = useRef(null);

  async function onFile(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setState({ status: "loading", name: file.name });
    try {
      const res = await scanMedicine(file);
      setState({ status: "ready", result: res.data });
    } catch (err) {
      const body = err.response?.data;
      // an unreadable photo still carries the photo notes, so the person knows what to fix
      if (err.response?.status === 422 && body) setState({ status: "unreadable", result: body });
      else setState({ status: "error", message: getErrorMessage(err) });
    }
  }

  const results = state.status === "ready" ? state.result.candidates : [];

  return (
    <Page
      crumbs={[{ label: "Dashboard", to: "/dashboard" }, { label: "Scan a medicine" }]}
      eyebrow="Medicine pack"
      title="Scan a medicine"
      subtitle="Photograph the front of a strip, box or bottle to see which products its text could mean, with price, maker and same-ingredient alternatives."
    >
      <section className="panel rise d1" style={{ display: "grid", gap: "var(--s-3)" }}>
        <input ref={inputRef} type="file" accept="image/png,image/jpeg" capture="environment" onChange={onFile} hidden aria-label="Photo of the medicine pack" />
        <div className="row" style={{ flexWrap: "wrap" }}>
          <button type="button" className="btn btn-primary" onClick={() => inputRef.current?.click()} disabled={state.status === "loading"}>
            <Camera size={16} /> {state.status === "loading" ? "Reading the pack…" : "Take or choose a photo"}
          </button>
          {state.status !== "idle" && state.status !== "loading" && (
            <button type="button" className="btn btn-ghost" onClick={() => setState({ status: "idle" })}><RotateCcw size={14} /> Start again</button>
          )}
        </div>
        <p className="tiny subtle">JPG or PNG. The photo is read once and not kept. A scan only suggests products: you choose, using what is printed on your pack.</p>
      </section>

      {state.status === "error" && <section className="panel" style={{ marginTop: "var(--s-5)" }}><ErrorState message={state.message} /></section>}
      {state.status === "unreadable" && (
        <section className="panel" style={{ marginTop: "var(--s-5)" }}>
          <div className="alert alert-warn">{state.result.message}. Retake it flat, in good light, with the name in focus.</div>
          <PhotoQualityNotes quality={state.result.image_quality} />
        </section>
      )}
      {state.status === "ready" && <section className="panel rise" style={{ marginTop: "var(--s-5)" }}><ScanResults result={state.result} onOpen={setSelected} /></section>}

      {selected && <MedicineDrawer medicine={selected} results={results} query="this scan" onClose={() => setSelected(null)} onExplain={setExplaining} />}
      {explaining && <ExplainDialog medicine={explaining} onClose={() => setExplaining(null)} />}
    </Page>
  );
}
