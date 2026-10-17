import { Pill, ScanLine, ShieldCheck, TrendingDown } from "lucide-react";
import Page from "./Page";

const POINTS = [
  { icon: ScanLine, text: "Reads typed and handwritten prescriptions" },
  { icon: Pill, text: "Matches every line to a real medicine" },
  { icon: TrendingDown, text: "Finds cheaper same-ingredient options" },
  { icon: ShieldCheck, text: "Checks interactions and your allergies" },
];

/** Two-panel frame for Login / Register: a short promise on the left, the form on the right. */
export default function AuthLayout({ crumbs, children }) {
  return (
    <Page crumbs={crumbs}>
      <div className="auth">
        <aside className="auth-aside rise" aria-hidden="true">
          <h2>Your prescription, decoded.</h2>
          <ul>
            {POINTS.map(({ icon: Icon, text }) => (
              <li key={text}><span><Icon size={17} /></span>{text}</li>
            ))}
          </ul>
          <div className="auth-aside-art"><i /><i /><i /></div>
        </aside>
        <div className="auth-main rise d1">{children}</div>
      </div>
    </Page>
  );
}
