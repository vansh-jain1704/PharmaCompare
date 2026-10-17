import SiteHeader from "./SiteHeader";
import BackLink from "./ui/BackLink";
import Breadcrumbs from "./ui/Breadcrumbs";
import { useAuth } from "../context/AuthContext";

/**
 * Standard page frame: header, then a content column that starts with the
 * contextual Back button and breadcrumbs, then the page title.
 *
 *   crumbs   [{label, to?}]  breadcrumb trail ending at this page
 *   back     {to, label}     parent for the Back button (default: dashboard)
 *   back={false}             omit the Back button
 *   width    "default" | "narrow"
 */
export default function Page({ children, width = "default", crumbs, back, title, subtitle, meta, actions, eyebrow }) {
  const { status } = useAuth();
  return (
    <div className={`page ${status === "authenticated" ? "has-tabbar" : ""}`}>
      <SiteHeader />
      <main className={`page-body ${width === "narrow" ? "page-narrow" : ""}`}>
        {(back !== false || crumbs) && (
          <div className="page-top">
            {back !== false && <BackLink to={back?.to} label={back?.label} />}
            <Breadcrumbs items={crumbs} />
          </div>
        )}
        {(title || actions) && (
          <div className="page-head rise">
            {eyebrow && <span className="eyebrow">{eyebrow}</span>}
            <div className="page-head-row">
              <div>
                {title && <h1>{title}</h1>}
                {subtitle && <p>{subtitle}</p>}
                {meta && <div className="page-meta">{meta}</div>}
              </div>
              {actions && <div className="page-head-actions">{actions}</div>}
            </div>
          </div>
        )}
        {children}
      </main>
    </div>
  );
}
