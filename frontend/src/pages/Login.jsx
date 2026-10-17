import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Clock } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { getErrorMessage } from "../api/getErrorMessage";
import AuthLayout from "../components/AuthLayout";
import PasswordInput from "../components/ui/PasswordInput";

export default function Login() {
  const { login } = useAuth();
  const location = useLocation();
  const justRegistered = Boolean(location.state?.registered);
  const expired = Boolean(location.state?.expired);

  const [form, setForm] = useState({ email: "", password: "" });
  const [fieldErrors, setFieldErrors] = useState({});
  const [serverError, setServerError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function handleChange(e) {
    setForm({ ...form, [e.target.name]: e.target.value });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setServerError("");
    const errors = {};
    if (!form.email.trim()) errors.email = "Email is required";
    if (!form.password) errors.password = "Password is required";
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    try {
      // GuestOnly sends the signed-in user on (back to where they were going).
      await login({ email: form.email.trim(), password: form.password });
    } catch (err) {
      setServerError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout crumbs={[{ label: "Home", to: "/" }, { label: "Log in" }]}>
      <form className="auth-card" onSubmit={handleSubmit} noValidate>
        <h1>Welcome back</h1>
        <p className="auth-sub">Log in to see your prescriptions and savings.</p>

        {expired && (
          <div className="alert alert-warn" role="status">
            <Clock size={16} style={{ flexShrink: 0, marginTop: 2 }} />
            <span>Your session ended, so we signed you out for safety. Log in again to pick up where you left off.</span>
          </div>
        )}
        {justRegistered && <div className="alert alert-ok">Account created. Please log in.</div>}
        {serverError && <div className="alert alert-risk" role="alert">{serverError}</div>}

        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" name="email" type="email" autoComplete="email" value={form.email} onChange={handleChange} />
          {fieldErrors.email && <span className="field-error">{fieldErrors.email}</span>}
        </div>

        <div className="field">
          <label htmlFor="password">Password</label>
          <PasswordInput id="password" name="password" autoComplete="current-password" value={form.password} onChange={handleChange} />
          {fieldErrors.password && <span className="field-error">{fieldErrors.password}</span>}
        </div>

        <button type="submit" className="btn btn-primary btn-block btn-lg" disabled={submitting}>
          {submitting ? <><span className="spinner" /> Signing in…</> : "Continue"}
        </button>

        <p className="auth-switch">New here? <Link to="/register">Create an account</Link></p>
      </form>
    </AuthLayout>
  );
}
