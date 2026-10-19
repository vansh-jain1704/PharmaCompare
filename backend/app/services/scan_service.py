"""
Scanning a medicine PACK (a strip, box or bottle) to find out what it is - the PPT's "scan medicines".

Packaging text is noisy (brand, composition, maker, MRP, batch, expiry, marketing words), and OCR cannot tell a genuine pack from a fake
one, so a scan NEVER confirms anything. It reads the text, runs the same matcher used for prescriptions over the text lines, and returns the
products that fit, best first, each with the reason it was offered. The person chooses, using what is printed on the pack. Nothing is
stored: the photo is processed from a temporary file and deleted.
"""
import re

from app.services.medicine_matching_service import match_line

# Packaging lines that say nothing about WHICH medicine it is (storage, batch and price, who made it, warnings). They would only add
# look-alikes by accident ("Store below 30 C" matched a product).
PACK_NOISE = re.compile(
    r"\b(store|keep|below|protect|away|reach|children|mrp|m\.r\.p|incl|taxes|batch|b\.?\s?no|lot|exp|expiry|mfg|mfd|manufactured|marketed|"
    r"limited|ltd|pvt|private|laboratories|pharma|healthcare|warning|schedule|rx|prescription|directions|dosage|as directed)\b",
    re.IGNORECASE,
)

MAX_LINES = 8          # matching a line costs a database search, so a pack is read from its first lines that look like names
MAX_CANDIDATES = 5

NOTICE = ("These are possible matches for the text read from the pack. They are not a confirmation: check the name, strength and maker printed "
          "on your pack against each one. A scan cannot tell whether a pack is genuine.")


def candidates_from_lines(lines, matcher=match_line):
    """
    The products the pack's text could mean, from its OCR lines. Returns [{"medicine_id", "score", "from_line", "settled_by_reader", "reasons"}],
    best first: a product the matcher settled on, then by score. A line the matcher skips (a heading, a warning, a date) offers nothing.
    """
    pool, considered = {}, 0
    for line in lines:
        text = (line.get("text") or "").strip()
        if not text or PACK_NOISE.search(text):
            continue
        if considered >= MAX_LINES:
            break
        result = matcher(text)
        if result["status"] == "skipped":
            continue
        considered += 1
        found = []
        if result["status"] == "matched" and result.get("medicine"):
            found.append((result["medicine"], result.get("confidence") or 0.0, True, []))
        else:
            for guess in result.get("guesses") or []:
                found.append((guess, guess.get("score") or 0.0, False, guess.get("reasons") or []))
            for option in result.get("options") or []:
                found.append((option, option.get("score") or 0.0, False, []))
            if result.get("medicine") and not result.get("guesses"):
                found.append((result["medicine"], result.get("confidence") or 0.0, False, []))
        for medicine, score, settled, reasons in found:
            current = pool.get(medicine["medicine_id"])
            if current is None or (settled, score) > (current["settled_by_reader"], current["score"]):
                pool[medicine["medicine_id"]] = {"medicine_id": medicine["medicine_id"], "score": round(float(score), 4), "from_line": text,
                                                 "settled_by_reader": settled, "reasons": reasons}
    ranked = sorted(pool.values(), key=lambda c: (not c["settled_by_reader"], -c["score"], c["medicine_id"]))
    return ranked[:MAX_CANDIDATES]
