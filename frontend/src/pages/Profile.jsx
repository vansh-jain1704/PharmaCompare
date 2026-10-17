import { Moon, ShieldAlert, Sun } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import Page from "../components/Page";
import { AllergySettings } from "../components/AllergyEditor";

export default function Profile() {
  const { user } = useAuth();
  const { theme, setTheme } = useTheme();
  return (
    <Page
      width="narrow"
      crumbs={[{ label: "Dashboard", to: "/dashboard" }, { label: "Profile" }]}
      eyebrow="Your account"
      title="Profile"
    >
      <section className="profile-card rise">
        <span className="avatar avatar-lg">{(user?.name || "?").charAt(0).toUpperCase()}</span>
        <div>
          <h2>{user?.name}</h2>
          <p className="muted small" style={{ margin: 0 }}>{user?.email}</p>
        </div>
      </section>

      <section className="panel rise d1" aria-labelledby="health-prefs">
        <div className="panel-head">
          <h2 id="health-prefs"><ShieldAlert size={18} /> Health preferences</h2>
          <p>
            Tell us about medicine allergies and we will flag matching medicines inside an analysis, only when they
            apply. No flag does not mean a medicine is safe for you. Always check with your doctor or pharmacist.
          </p>
        </div>
        <AllergySettings />
      </section>

      <section className="panel rise d2" aria-labelledby="appearance">
        <div className="panel-head">
          <h2 id="appearance">Appearance</h2>
          <p>Choose how PharmaCompare looks. You can also switch from the header on any page.</p>
        </div>
        <div className="seg" role="group" aria-label="Theme">
          <button type="button" className={theme === "light" ? "is-on" : ""} aria-pressed={theme === "light"} onClick={() => setTheme("light")}><Sun size={15} /> Light</button>
          <button type="button" className={theme === "dark" ? "is-on" : ""} aria-pressed={theme === "dark"} onClick={() => setTheme("dark")}><Moon size={15} /> Dark</button>
        </div>
      </section>
    </Page>
  );
}
