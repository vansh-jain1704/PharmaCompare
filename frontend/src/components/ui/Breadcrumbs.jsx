import { Fragment } from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

/** items: [{ label, to? }] - the last item is the current page and is not a link. */
export default function Breadcrumbs({ items }) {
  if (!items || items.length === 0) return null;
  return (
    <nav aria-label="Breadcrumb">
      <ol className="crumbs">
        {items.map((item, i) => {
          const last = i === items.length - 1;
          return (
            <Fragment key={`${item.label}-${i}`}>
              <li>
                {last || !item.to
                  ? <span aria-current={last ? "page" : undefined}>{item.label}</span>
                  : <Link to={item.to}>{item.label}</Link>}
              </li>
              {!last && <li aria-hidden="true"><ChevronRight size={14} /></li>}
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
