import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, ArrowRight, CheckCircle2, FileText, History, Lightbulb, MapPin, Pill, ScanSearch, Search, Wallet } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import Page from "../components/Page";
import { listPrescriptions } from "../api/prescriptionApi";
import usePrescriptionSummaries from "../hooks/usePrescriptionSummaries";
import useCountUp from "../hooks/useCountUp";
import { formatDate, prescriptionTitle, rupees } from "../utils/format";

const ACTIONS = [
  { to: "/upload", icon: ScanSearch, title: "Analyze Prescription", text: "Upload a photo or PDF and get a full medicine report.", tone: "purple", primary: true },
  { to: "/search", icon: Search, title: "Search Medicines", text: "Look up any brand or salt: price, maker, alternatives.", tone: "teal" },
  { to: "/stores", icon: MapPin, title: "Find Stores Near Me", text: "Medical stores and Jan Aushadhi Kendras near you, on a map.", tone: "purple" },
  { to: "/prescriptions", icon: History, title: "View History", text: "Every analysis you have run, with its savings.", tone: "orange" },
];

function Metric({ icon: Icon, label, value, format, tone, loading }) {
  const n = useCountUp(loading ? 0 : value, { duration: 800 });
  return (
    <div className={`metric tone-${tone}`}>
      <span className="metric-icon"><Icon size={18} /></span>
      <div>
        <div className="metric-value num">{loading ? <span className="skeleton metric-skel" /> : format(n)}</div>
        <div className="metric-label">{label}</div>
      </div>
    </div>
  );
}

/** One or two plain sentences about the latest analysis, built from its real numbers (no model involved). */
function buildInsight(latest, summary) {
  if (!latest) return { text: "Upload your first prescription to see what it contains, what needs checking and where you could save.", cta: null };
  if (!summary) return { text: "Reading your latest analysis…", cta: null };
  const parts = [];
  parts.push(`${summary.identified} of ${summary.detected} medicine${summary.detected === 1 ? "" : "s"} identified`
    + (summary.needsVerification > 0 ? `, ${summary.needsVerification} still need${summary.needsVerification === 1 ? "s" : ""} your confirmation.` : "."));
  parts.push(summary.savings > 0
    ? `Cheaper same-ingredient options could save ${rupees(summary.savings)}${summary.savingsPercent != null ? ` (${Math.round(summary.savingsPercent)}% lower)` : ""}.`
    : "No cheaper equivalent was found on file.");
  if (summary.allergyAlerts > 0) parts.push("An allergy alert applies, so check it before using anything.");
  return { text: parts.join(" "), cta: { to: `/prescriptions/${latest.prescription_id}`, label: "View analysis" } };
}

export default function Dashboard() {
  const { user } = useAuth();
  const [list, setList] = useState({ status: "loading", items: [] });

  useEffect(() => {
    let cancelled = false;
    listPrescriptions()
      .then((res) => !cancelled && setList({ status: "ready", items: res.data.prescriptions }))
      .catch(() => !cancelled && setList({ status: "ready", items: [] }));
    return () => { cancelled = true; };
  }, []);

  const { summaries, loading: summariesLoading } = usePrescriptionSummaries(list.items);

  const totals = useMemo(() => {
    const done = list.items.map((p) => summaries[p.prescription_id]).filter(Boolean);
    return {
      analyzed: list.items.filter((p) => p.status === "processed").length,
      identified: done.reduce((n, s) => n + s.identified, 0),
      savings: done.reduce((n, s) => n + s.savings, 0),
      verify: done.reduce((n, s) => n + s.needsVerification, 0),
    };
  }, [list.items, summaries]);

  const loading = list.status === "loading" || (list.items.length > 0 && summariesLoading);
  const latest = list.items[0];
  const insight = buildInsight(latest, latest && summaries[latest.prescription_id]);
  const recent = list.items.slice(0, 3);

  return (
    <Page back={false} title={`Hi, ${user?.name?.split(" ")[0] || "there"}`} subtitle="What would you like to do today?">
      <div className="action-grid rise d1">
        {ACTIONS.map(({ to, icon: Icon, title, text, tone, primary }) => (
          <Link to={to} className={`action tone-${tone} ${primary ? "is-primary" : ""}`} key={to}>
            <span className="action-icon"><Icon size={24} /></span>
            <h3>{title}</h3>
            <p>{text}</p>
            <ArrowRight size={18} className="action-arrow" aria-hidden="true" />
          </Link>
        ))}
      </div>

      <section className="overview rise d2" aria-label="Quick overview">
        <h2 className="section-label">Quick overview</h2>
        <div className="metrics">
          <Metric icon={FileText} label="Prescriptions analyzed" value={totals.analyzed} format={(n) => Math.round(n)} tone="purple" loading={list.status === "loading"} />
          <Metric icon={Pill} label="Medicines identified" value={totals.identified} format={(n) => Math.round(n)} tone="teal" loading={loading} />
          <Metric icon={Wallet} label="Potential savings" value={totals.savings} format={(n) => rupees(n)} tone="teal" loading={loading} />
          <Metric icon={AlertCircle} label="Need verification" value={totals.verify} format={(n) => Math.round(n)} tone="orange" loading={loading} />
        </div>
      </section>

      <div className="dash-lower rise d3">
        <section className="insight" aria-label="Smart insight">
          <span className="insight-icon"><Lightbulb size={20} /></span>
          <div>
            <h2 className="section-label">Smart insight</h2>
            <p>{insight.text}</p>
            {insight.cta && <Link to={insight.cta.to} className="link-btn">{insight.cta.label} <ArrowRight size={13} /></Link>}
            <span className="insight-note">Summarised from your latest analysis. Not medical advice.</span>
          </div>
        </section>

        <section className="recent" aria-label="Recent analyses">
          <div className="row-between">
            <h2 className="section-label">Recent analyses</h2>
            {list.items.length > 0 && <Link to="/prescriptions" className="link-btn">See all <ArrowRight size={13} /></Link>}
          </div>
          {list.status === "loading" && <div className="stack"><div className="skeleton" style={{ height: 52 }} /><div className="skeleton" style={{ height: 52 }} /></div>}
          {list.status === "ready" && recent.length === 0 && (
            <p className="small muted" style={{ margin: 0 }}>Nothing here yet. <Link to="/upload" className="link-btn">Analyze your first prescription</Link></p>
          )}
          <ul className="recent-list">
            {recent.map((p) => {
              const s = summaries[p.prescription_id];
              return (
                <li key={p.prescription_id}>
                  <Link to={`/prescriptions/${p.prescription_id}`} className="recent-row">
                    <span className="recent-icon">{s && s.needsVerification === 0 ? <CheckCircle2 size={17} /> : <FileText size={17} />}</span>
                    <span className="recent-main">
                      <strong>{prescriptionTitle(p)}</strong>
                      <span>{s ? `${s.detected} medicine${s.detected === 1 ? "" : "s"}${s.savings > 0 ? ` • ${rupees(s.savings)} potential savings` : ""}` : formatDate(p.upload_date)}</span>
                    </span>
                    <ArrowRight size={15} aria-hidden="true" />
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      </div>
    </Page>
  );
}
