import { useEffect, useState } from "react";
import axiosClient from "../api/axiosClient";
import PriceSources from "./results/PriceSources";

const KIND_LABELS = {
  reference_dataset: "Medicine reference data",
  interaction_dataset: "Interaction data",
  pharmacy_feed: "Pharmacy feed",
  synthetic_demo: "Demo data (not real)",
};

function formatDate(iso) {
  return iso ? new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "not recorded";
}

function formatDateTime(iso) {
  return iso ? new Date(iso).toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : null;
}

/** The outside services, whether each is configured (never a key) and what the app does without it. "Configured" is not "up": nothing is pinged. */
export function ExternalServices({ services }) {
  if (!services?.length) return null;
  return (
    <div style={{ marginTop: "var(--s-5)" }}>
      <h3 className="detail-h">Outside services</h3>
      <ul className="bullets" style={{ listStyle: "none", paddingLeft: 0, display: "grid", gap: "var(--s-3)" }}>
        {services.map((s) => (
          <li key={s.key}>
            <strong>{s.name}</strong> <span className={`pa-pill ${s.configured ? "is-ok" : "is-muted"}`}>{s.configured ? "Configured" : "Not configured"}</span>
            <div className="small muted">If it is unavailable: {s.when_unavailable}</div>
          </li>
        ))}
      </ul>
      <p className="tiny subtle">“Configured” means set up on this server, not that the service is working right now.</p>
    </div>
  );
}

/** The registry as given by the backend: what each source is, its size, when it was obtained, its licence AS RECORDED, and how good it measures. */
export function DataSourcesList({ sources, live = null, services = null }) {
  if (!sources.length) return <p className="small muted">No data sources are registered yet.</p>;
  return (
    <>
      <PriceSources live={live} />
      <ul className="bullets" style={{ listStyle: "none", paddingLeft: 0, display: "grid", gap: "var(--s-4)" }}>
      {sources.map((s) => (
        <li key={s.source_key}>
          <strong>{s.name}</strong>{" "}
          <span className={`tag ${s.demo ? "tag-warning" : ""}`}>{KIND_LABELS[s.kind] || s.kind}</span>
          <div className="small muted">
            {s.record_count != null && `${s.record_count.toLocaleString("en-IN")} record${s.record_count === 1 ? "" : "s"} · `}
            obtained {formatDate(s.retrieved_at)} · licence: {s.license_recorded ? s.license : "not recorded"}
            {s.pharmacies != null && ` · ${s.pharmacies} pharmacies, ${s.observations} reports`}
          </div>
          {s.pharmacies != null && (
            <div className="small muted">
              {s.latest_observed_at
                ? `newest report observed ${formatDateTime(s.latest_observed_at)} · last data received ${formatDateTime(s.latest_received_at)}`
                : "nothing has been reported by this feed yet"}
            </div>
          )}
          {s.notes && <p className="small" style={{ margin: "0.3rem 0 0" }}>{s.notes}</p>}
          {s.url && <p className="tiny subtle" style={{ margin: "0.2rem 0 0" }}>{s.url}</p>}
        </li>
      ))}
      </ul>
      <ExternalServices services={services} />
    </>
  );
}

export default function DataSources() {
  const [state, setState] = useState({ status: "loading", sources: [], live: null, services: null });
  useEffect(() => {
    let cancelled = false;
    axiosClient.get("/api/data-sources")
      .then((res) => { if (!cancelled) setState({ status: "ready", sources: res.data.sources || [], live: res.data.live_data || null, services: res.data.external_services || null }); })
      .catch(() => { if (!cancelled) setState({ status: "error", sources: [] }); });
    return () => { cancelled = true; };
  }, []);
  if (state.status === "loading") return <p className="small muted">Loading data sources…</p>;
  if (state.status === "error") return <p className="small muted">The list of data sources could not be loaded right now.</p>;
  return <DataSourcesList sources={state.sources} live={state.live} services={state.services} />;
}
