import { useEffect, useState } from "react";
import { fetchCurrentUser, updateAllergies } from "../api/authApi";
import { getErrorMessage } from "../api/getErrorMessage";

export const ALLERGY_CHIPS = ["Penicillin", "Sulfa", "NSAIDs"];

const sameName = (a, b) => a.trim().toLowerCase() === b.trim().toLowerCase();

export function parseAllergyText(text) {
  return text.split(/[,;\n]+/).map((t) => t.trim()).filter(Boolean);
}

/**
 * Free-text allergies plus quick-pick chips. Controlled by an array of
 * strings; the backend does the matching, so this only collects them.
 * The text box holds whatever isn't one of the chips.
 */
export default function AllergyEditor({ value, onChange, disabled = false }) {
  const chips = ALLERGY_CHIPS.filter((c) => value.some((v) => sameName(v, c)));
  const others = value.filter((v) => !ALLERGY_CHIPS.some((c) => sameName(v, c)));
  const [text, setText] = useState(others.join(", "));

  // Keep the box in step when the list is replaced from outside (e.g. loaded from the server).
  const othersKey = others.join("|");
  useEffect(() => {
    if (parseAllergyText(text).join("|") !== othersKey) setText(others.join(", "));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [othersKey]);

  function toggleChip(chip) {
    const next = chips.includes(chip) ? chips.filter((c) => c !== chip) : [...chips, chip];
    onChange([...next, ...others]);
  }

  function handleText(e) {
    setText(e.target.value);
    onChange([...chips, ...parseAllergyText(e.target.value)]);
  }

  return (
    <div className="allergy-editor">
      <div className="chip-grid" role="group" aria-label="Common allergies">
        {ALLERGY_CHIPS.map((c) => (
          <button
            type="button" key={c} disabled={disabled}
            className={`chip ${chips.includes(c) ? "is-selected" : ""}`}
            aria-pressed={chips.includes(c)} onClick={() => toggleChip(c)}
          >
            {c}
          </button>
        ))}
      </div>
      <div className="field" style={{ marginTop: "var(--s-3)" }}>
        <label htmlFor="allergy-other">Allergies (if any)</label>
        <input
          id="allergy-other" type="text" value={text} onChange={handleText} disabled={disabled}
          placeholder="Anything else, separated by commas - e.g. Aspirin, Latex"
          maxLength={400}
        />
      </div>
    </div>
  );
}

/** Loads, edits and saves the signed-in user's allergies (used on the dashboard). */
export function AllergySettings() {
  const [list, setList] = useState([]);
  const [status, setStatus] = useState("loading"); // loading | idle | saving | saved | error
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchCurrentUser()
      .then((res) => { if (!cancelled) { setList(res.data.user.allergies || []); setStatus("idle"); } })
      .catch((err) => { if (!cancelled) { setError(getErrorMessage(err)); setStatus("error"); } });
    return () => { cancelled = true; };
  }, []);

  async function save() {
    setStatus("saving");
    setError("");
    try {
      const res = await updateAllergies(list);
      setList(res.data.allergies);
      setStatus("saved");
    } catch (err) {
      setError(getErrorMessage(err));
      setStatus("error");
    }
  }

  if (status === "loading") return <p className="small muted">Loading your allergies…</p>;

  return (
    <div>
      <AllergyEditor
        value={list} disabled={status === "saving"}
        onChange={(next) => { setList(next); if (status === "saved") setStatus("idle"); }}
      />
      {error && <div className="alert alert-risk" style={{ marginTop: "var(--s-3)" }}>{error}</div>}
      <div className="row" style={{ marginTop: "var(--s-3)", alignItems: "center", gap: "var(--s-3)" }}>
        <button type="button" className="btn btn-primary btn-sm" onClick={save} disabled={status === "saving"}>
          {status === "saving" ? "Saving…" : "Save allergies"}
        </button>
        {status === "saved" && <span className="small muted" role="status">Saved. Your prescriptions were re-checked.</span>}
      </div>
    </div>
  );
}
