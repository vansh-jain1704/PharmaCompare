import { useEffect, useState } from "react";
import { getPrescription } from "../api/prescriptionApi";
import { summarizeDetail } from "../utils/summary";

// Detail records are fetched once per session and reused, so moving between
// the dashboard and history does not refetch everything.
const cache = new Map();

export function invalidateSummary(id) {
  cache.delete(id);
}

const BATCH = 4;

/**
 * Loads a summary for each prescription in `list`, a few at a time.
 * Returns { summaries: {id: summary | null}, loading }. A prescription whose
 * detail fails to load gets `null` (so the UI can show its row without
 * numbers) rather than failing the whole list.
 */
export default function usePrescriptionSummaries(list) {
  const [summaries, setSummaries] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      for (let i = 0; i < list.length; i += BATCH) {
        const batch = list.slice(i, i + BATCH);
        const results = await Promise.allSettled(batch.map(async (p) => {
          if (!cache.has(p.prescription_id)) {
            const res = await getPrescription(p.prescription_id);
            cache.set(p.prescription_id, summarizeDetail(res.data));
          }
          return cache.get(p.prescription_id);
        }));
        if (cancelled) return;
        setSummaries((prev) => {
          const next = { ...prev };
          results.forEach((r, idx) => { next[batch[idx].prescription_id] = r.status === "fulfilled" ? r.value : null; });
          return next;
        });
      }
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [list]);

  return { summaries, loading };
}
