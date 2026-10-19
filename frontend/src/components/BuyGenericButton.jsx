import { useState } from "react";
import { ShoppingCart } from "lucide-react";
import { SEARCH_SITE } from "../utils/buyGeneric";

/** What a person is told when a medicine cannot be searched yet. It asks for verification and never offers a guess. */
export function VerifyFirstNote({ reason, onVerify, floating = false }) {
  return (
    <span className={`buy-generic-note ${floating ? "is-floating" : ""}`} role="note">
      <strong>Verify this medicine first.</strong> {reason} We will not guess which product to search for.
      {onVerify && <button type="button" className="link-btn" onClick={onVerify}>Verify now</button>}
    </span>
  );
}

/**
 * "Buy Generic", beside a medicine's name. With a settled medicine it is a plain link to a web search (a new tab, no referrer, nothing but the
 * ingredients, strength and form in the address). Without one it is a button that asks the person to verify the medicine and says why.
 *
 *   verdict    the result of productBuyGeneric / rowBuyGeneric
 *   onVerify   opens the verify step for this medicine, when there is one
 *   floating   the note floats under the button (used where the button sits in a card)
 */
export default function BuyGenericButton({ verdict, onVerify, floating = false }) {
  const [open, setOpen] = useState(false);
  const stop = (event) => event.stopPropagation();

  if (verdict?.ok) {
    return (
      <a
        className="buy-generic"
        href={verdict.url}
        target="_blank"
        rel="noopener noreferrer"
        onClick={stop}
        title={`Opens a ${SEARCH_SITE} search for ${verdict.query} in a new tab. PharmaCompare shows no price or stock for it.`}
        aria-label={`Buy Generic: search ${SEARCH_SITE} for ${verdict.query} (opens in a new tab)`}
      >
        <ShoppingCart size={12} aria-hidden="true" /> Buy Generic
      </a>
    );
  }
  return (
    <span className="buy-generic-wrap" onClick={stop}>
      <button
        type="button"
        className="buy-generic is-unverified"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        title="This medicine needs to be verified before it can be searched."
      >
        <ShoppingCart size={12} aria-hidden="true" /> Buy Generic
      </button>
      {open && <VerifyFirstNote reason={verdict?.reason} onVerify={onVerify ? () => { setOpen(false); onVerify(); } : undefined} floating={floating} />}
    </span>
  );
}
