import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import Page from "../components/Page";
import AllergyEditor from "../components/AllergyEditor";
import { updateAllergies } from "../api/authApi";
import { getErrorMessage } from "../api/getErrorMessage";
import { onboardingKey } from "../utils/onboarding";

/**
 * One optional question, shown once after a user's first login: any medicine
 * allergies? Answers are saved with the existing allergies endpoint; skipping
 * saves nothing. They can be changed later under Profile, Health preferences.
 */
export default function Onboarding() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [allergies, setAllergies] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function markDone() {
    if (user?.user_id != null) localStorage.setItem(onboardingKey(user.user_id), "1");
    navigate("/dashboard");
  }

  async function handleContinue() {
    if (allergies.length === 0) { markDone(); return; }
    setSaving(true);
    setError("");
    try {
      await updateAllergies(allergies);
      markDone();
    } catch (err) {
      setError(getErrorMessage(err));
      setSaving(false);
    }
  }

  return (
    <Page width="narrow" back={false} crumbs={[{ label: "Welcome" }, { label: "Health preferences" }]}>
      <div className="auth-card auth-card-wide rise">
        <h1>Hi, {user?.name?.split(" ")[0] || "there"}. Any medicine allergies?</h1>
        <p className="auth-sub">
          Optional. We will flag a medicine only when it contains something you are allergic to, and only inside an
          analysis. You can change this any time under Profile.
        </p>
        <AllergyEditor value={allergies} onChange={setAllergies} disabled={saving} />
        {error && <div className="alert alert-risk" role="alert" style={{ marginTop: "var(--s-3)" }}>{error}</div>}
        <div className="auth-actions">
          <button type="button" className="btn btn-ghost" onClick={markDone} disabled={saving}>Skip for now</button>
          <button type="button" className="btn btn-primary" onClick={handleContinue} disabled={saving}>
            {saving ? "Saving…" : "Continue"} <ArrowRight size={16} />
          </button>
        </div>
      </div>
    </Page>
  );
}
