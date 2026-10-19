import { Factory } from "lucide-react";
import BuyGenericButton from "./BuyGenericButton";
import { hasWarning } from "../utils/dataNotes";
import { productBuyGeneric } from "../utils/buyGeneric";
import { rupees } from "../utils/format";

/**
 * One medicine in the search results. The card opens the details; "Buy Generic" sits beside the name as its own control, outside the card's button
 * (a link cannot live inside a button).
 */
export default function MedicineResultCard({ medicine: m, index = 0, onOpen }) {
  return (
    <div className={`med-card-wrap rise ${index < 6 ? `d${(index % 5) + 1}` : ""}`}>
      <button type="button" className="med-card" onClick={() => onOpen(m)} aria-label={`Open details for ${m.medicine_name}`}>
        <span className="med-card-top">
          <strong>{m.medicine_name}</strong>
          {m.is_discontinued && <span className="pill tone-risk">Discontinued</span>}
        </span>
        <span className="med-comp">{m.composition || "Composition not on file"}</span>
        <span className="med-meta">{[m.strength, m.form].filter(Boolean).join(" · ")}</span>
        {hasWarning(m.data_notes) && <span className="tag tag-warning">Check data notes</span>}
        <span className="med-maker"><Factory size={12} /> {m.manufacturer || "Maker not on file"}</span>
        <span className="med-bottom"><b className="num">{rupees(m.price)}</b><span className="med-more">Compare →</span></span>
      </button>
      <div className="med-card-buy">
        <BuyGenericButton verdict={productBuyGeneric(m)} onVerify={() => onOpen(m)} floating />
      </div>
    </div>
  );
}
