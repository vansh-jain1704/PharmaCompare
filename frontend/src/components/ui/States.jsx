import { AlertTriangle, CheckCircle2, Inbox, Loader2 } from "lucide-react";

/**
 * The four states every data surface needs. Having them as one vocabulary
 * stops each page inventing its own spinner and its own "nothing here yet".
 */

export function Spinner({ size = "sm", label }) {
  return (
    <span className="row" role="status" aria-live="polite">
      <span className={`spinner ${size === "lg" ? "spinner-lg" : ""}`} />
      {label && <span className="small muted">{label}</span>}
      <span className="sr-only">{label || "Loading"}</span>
    </span>
  );
}

export function LoadingState({ title = "Loading", message }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="state-icon">
        <Loader2 size={26} className="spin-icon" style={{ animation: "spin 900ms linear infinite" }} />
      </span>
      <h3>{title}</h3>
      {message && <p>{message}</p>}
    </div>
  );
}

/**
 * Skeletons mirror the shape of what's coming, so the layout doesn't jump
 * when real content lands.
 */
export function SkeletonCard({ lines = 3 }) {
  return (
    <div className="card panel" aria-hidden="true">
      <div className="skeleton skeleton-line w-40" />
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className={`skeleton skeleton-line ${i % 2 ? "w-60" : "w-80"}`} />
      ))}
    </div>
  );
}

export function SkeletonRows({ rows = 3 }) {
  return (
    <div className="stack" aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 64 }} />
      ))}
    </div>
  );
}

export function EmptyState({ icon, title, message, action }) {
  return (
    <div className="state">
      <span className="state-icon">{icon || <Inbox size={26} />}</span>
      <h3>{title}</h3>
      {message && <p>{message}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ title = "Something went wrong", message, action }) {
  return (
    <div className="state" role="alert">
      <span className="state-icon is-risk"><AlertTriangle size={26} /></span>
      <h3>{title}</h3>
      {message && <p>{message}</p>}
      {action}
    </div>
  );
}

export function SuccessState({ title, message, action }) {
  return (
    <div className="state">
      <span className="state-icon is-ok"><CheckCircle2 size={26} /></span>
      <h3>{title}</h3>
      {message && <p>{message}</p>}
      {action}
    </div>
  );
}
