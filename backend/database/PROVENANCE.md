# Medicines table - data provenance

## Source

- **Dataset:** [Indian-Medicine-Dataset](https://github.com/junioralive/Indian-Medicine-Dataset) by junioralive (GitHub)
- **File imported:** `DATA/indian_medicine_data.csv`
- **License:** MIT (see the repo's `LICENSE` file) - permits use, modification, and redistribution
- **Imported on:** see `Medicines.imported_at` per row; the import script records the exact date
- **Row count at import:** 253,973

## What this is NOT

This is a **community-compiled reference dataset**, not an official or government-verified
source. The repository does not state where the original data was compiled from. It is
used here for local, offline medicine-name and composition matching against OCR output -
**not** presented to users as clinically verified or government-sourced data.

Every row imported from it is tagged `data_source = 'community_dataset:indian-medicine-dataset-github'`
in the `Medicines` table, so this can never be silently confused with a future, more
authoritative source (see "Future upgrade path" below).

## Why this dataset was chosen

Documented in the PharmaCompare project conversation history: compared against India's new
government "Drug Registry" (launched June 2026, CDSCO/NRCeS/ABDM), RxNorm/RxNav (NIH, US-focused),
and NPPA/Jan Aushadhi (official but PDF-only, no API). This dataset was chosen because it is
free, immediately usable with no registration friction, has clean composition/strength/manufacturer/price
fields for 253,973 real Indian medicine products, and is MIT-licensed.

## Known limitations

- Original data provenance is not stated by the dataset author.
- Static snapshot - not updated on any schedule; prices and discontinued status may be stale.
- No official verification of accuracy.
- `form` (dosage form) is derived locally at import time via keyword matching on the medicine
  name (e.g. "Tablet", "Syrup"), not a field in the original dataset - it covers ~99.2% of rows;
  the rest are left `NULL` rather than guessed.

## Future upgrade path

India's government "Drug Registry" (drugregistrybeta.abdm.gov.in) is the intended long-term
authoritative source once its public developer access terms are confirmed. When adopted, its
rows would be tagged with a different `data_source` value, and matching logic can prefer
government-sourced rows over community-sourced ones without needing a schema change.

---

# Drug_Interactions table - data provenance

## Source

- **Dataset:** [DDInter 2.0](https://ddinter2.scbdd.com/) - a peer-reviewed drug-drug
  interaction database published in *Nucleic Acids Research* (Oxford Academic):
  ["DDInter 2.0: an enhanced drug interaction resource..."](https://academic.oup.com/nar/article/53/D1/D1356/7740584)
- **Files imported:** all 8 category CSVs from the public download page
  (`ddinter_downloads_code_{A,B,D,H,L,P,R,V}.csv`), stored locally at `database/data/ddinter/`
- **Access:** free, no registration required
- **Imported on:** see `Drug_Interactions.imported_at`; import script records the exact date
- **Row count at import:** 222,383 raw rows across the 8 files -> 160,235 unique pairs after
  deduplication (the same pair can appear in more than one therapeutic-category file)

## What this IS

A real, peer-reviewed academic reference for known drug-drug interactions, each pair
carrying DDInter's own severity scale verbatim: `Major`, `Moderate`, `Minor`, or `Unknown`
(DDInter records that a pair interacts but hasn't established a severity for it - kept as
its own status, never silently upgraded or downgraded to another severity).

## What this is NOT, and how the app enforces it

**PharmaCompare is not a diagnosis system, and DDInter coverage is not exhaustive.**
This is enforced in application code (`app/services/clinical_decision_service.py`), not
just in this document:
- A pair with **no** row here is reported as `NEEDS_VERIFICATION`, never as "no interaction"
  or "safe". Absence of a record is absence of information, not evidence of safety.
- Drug names are matched against our `Medicines.primary_salt` by exact (then salt-form-normalized)
  string match. Coverage check at import time: **~56% of our distinct salts have an exact-or-normalized
  match in DDInter's ~1,939 tracked substances.** Anything outside that coverage is also
  `NEEDS_VERIFICATION`.
- Findings never instruct the user to stop, start, or change a prescribed medicine - every
  non-trivial finding's recommendation is to verify with a doctor or pharmacist.

## Known limitations

- The public bulk CSV download provides drug pairs + severity level only - **no mechanism
  description or management-recommendation text**, even though DDInter's own website shows
  richer detail per pair on their web interface. Our `explanation` field is generated from
  the pair + severity only, not from unavailable mechanism text - never fabricated.
- Drug names are DDInter's own international/generic naming (e.g. "Epinephrine"), which does
  not always match this project's community medicine dataset's spelling (e.g. "Amoxycillin"
  vs "Amoxicillin") - matching handles this partially (exact + salt-form-suffix normalization),
  not with an invented synonym dictionary.
