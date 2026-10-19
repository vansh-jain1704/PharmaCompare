# Demo guide: the "Needs verification" workflow

Everything below was run end to end on the real app (Google Vision OCR, the real matcher, the real MySQL database)
with the synthetic prescription in this folder. The expected screens are what that run showed. Nothing here is a real
patient, doctor or clinic, and nothing is medical advice.

## Before the review

1. MySQL is running, then start the app (`start-pharmacompare.bat`, or the two servers by hand). Wait for the backend
   window to print `Running on http://127.0.0.1:5000` (about 30 s: it loads the OCR libraries).
2. Open http://localhost:5173 and **register a demo account** (any name, an address like `demo@example.invalid`).
   Do not use a real person's account for the review.
3. The test image is `demo/synthetic_prescription.png`. To recreate it:
   `backend\venv\Scripts\python.exe demo\make_synthetic_prescription.py`
4. OCR needs `GOOGLE_VISION_API_KEY` in `backend\.env` (the image is sent to Google). Without it the app falls back to the
   local reader, which is weaker; rehearse once with whichever you will use on the day.

## What the test page contains, and what the system should do with each line

| Line on the page | Expected outcome | Why |
|---|---|---|
| 1. Tab Dolo 650 1-0-1 for 5 days | **Matched**, 100% confidence, priced, alternative and saving shown | Every word of the line is in the product name |
| 2. Tab Azee 500 1-0-0 for 3 days | **Matched**, 100%, priced, saving shown | Same |
| 3. Cap Omez 20 1-0-0 for 7 days | **Check match**: "Form differs from the prescription" | Matched to *Omez FF 20 Tablet*, but the line says capsule. It is held out of the savings total until you look at it |
| 4. Tab Zincovit 1-0-0 for 10 days | **Needs verification**, closest guess 80% | *Zincovit* is not in the dataset; only look-alikes (*Zincold Tablet*, *Zincast Tablet*, *Zincovec 50 Tablet*) exist |
| 5. Tab Shelcal 500 0-1-0 for 30 days | **Needs verification**, no candidates | Nothing on file resembles *Shelcal* |

Header after upload (View Analysis): **5 medicines detected, 2 automatically matched, 3 needs verification**;
estimated savings counted across **2 of 5** medicines (lines 4 and 5 have no price; line 3 is awaiting a check).

## The demonstration, step by step

**1. Upload.** Analyze → choose `synthetic_prescription.png` → Analyze Prescription → View Analysis.
Point out: lines 4 and 5 say *Needs verification*, strength/form say *Needs confirmation*, and price, alternative
and savings say *Identify the medicine first*. They are **not** in any price comparison (this is the gate).

**2. Read why.** Row 4 shows the text as read, `Closest guess: 80%`, *Only look-alike products found* and
`Closest look-alike, not confirmed: Zincold Tablet`. Click **View**: *Why this needs verification* explains in words
that the name is only similar and below the 90% needed to accept a look-alike, lists the three look-alikes (ingredients,
strength, form, similarity %) and offers **Review this**, **Verify**, and **None of these**.

**3. Try to confirm a wrong product (the safety net).** Click **Verify** on row 4. The dialog shows the line, the
reasons and the three look-alikes marked *not confirmed*. Search `Zincold Syrup`, select it, press **Confirm medicine**.
Expected: **"Check this before you confirm"**: *the prescription line points to a tablet, but "Zincold Syrup" is a syrup*,
plus *the name is only similar*, and the statement that confirming only records your decision and does not show the
product matches the prescription or is medically equivalent. Nothing has been saved. Press **Go back**.

**4. Say "none of these".** In the same dialog press **None of these**. After the refresh (about 5 s) row 4 reads
**Not identified (by you)**, *Marked by you*, button **Review again**; the header drops to 2 needing verification.
It is still not priced.

**5. Confirm one by hand, with a warning.** Row 5 → **Verify** → the reason is *No product on file resembles this text*.
Search `calcium carbonate vitamin d3`, select *Cavit-XT Tablet*, press **Confirm medicine**. Expected warning: *the line
does not look like "Cavit-XT Tablet"*. Press **Confirm anyway - I checked my prescription**. After the refresh row 5
shows *Cavit-XT Tablet*, **Confirmed**, *Confirmed by you*, with the original text still beneath it
(`5. Tab Shelcal 500 0-1-0 for 30 days`) and a newly computed reference price (₹316.50 in our run).
Click **View**: *Your decision* says you chose it, were shown differences, and that PharmaCompare has not verified it.

**5b. A "Check match" line.** Row 3 (Omez) → **View** → **Confirm this match**. Expected: the same **"Check this before
you confirm"** dialog: *the prescription line points to a capsule, but "Omez FF 20 Tablet" is a tablet*. Press **Confirm anyway**.
Row 3 then reads **Confirmed · Confirmed by you · Differs from the prescription line**. Its comparison (82% lower in our
run) is still shown, but **the headline savings do not include it**: the panel explains that the price comparison describes
the product you chose, which may not be the medicine prescribed. The same rule applies to row 5 after step 5.

**6. Prove it was saved.**
- Reload the page: rows 4 and 5 keep their states.
- *Download Report* / *Generate Smart Health Report*: the PDF uses the same words (*Not identified (by you)*, *Confirmed*, *Check match*).
- The review trail, in MySQL:
  ```sql
  SELECT log_id, timestamp, details FROM System_Logs WHERE action = 'medicine_verification' ORDER BY log_id DESC LIMIT 5;
  SELECT pm_id, raw_text, match_status, medicine_id FROM Prescription_Medicines WHERE prescription_id = <id from the URL>;
  ```
  Each log row holds the line's text as read, its status and confidence *before* your decision, the candidates you were
  shown, the warnings shown and whether you acknowledged them. `raw_text` in `Prescription_Medicines` is unchanged.

**7. Clean up.** History → delete the demo prescription (its review-trail rows are deleted with it).

## What to say, and what not to say

- A confirmation that conflicts with the line is **kept as your decision but never adds to the headline savings**; a
  confirmation with no conflict, or a product added by hand, counts as usual. The PDF applies the same rule and says so
  ("Not counted: confirmed despite differences from the line").
- Every decision on a line is listed under **Decision history** in its detail (oldest first); the original line is never altered.
- Prices are **reference prices from a community dataset snapshot**, not live pharmacy prices, and availability is **not tracked**.
- A manual confirmation is **your decision**. The app flags differences but never proves equivalence.
- The 90% automatic-acceptance bar and the other thresholds are constants in `backend/app/services/medicine_matching_service.py`.
  The comment that justifies 90% cites a test file that is not in the repository, so the figure is not reproducible from the repo.
- Handwriting accuracy has not been measured on a labelled set; do not quote one.
- Durations are written "for N days" on the test page on purpose: OCR reads a lone "x" with low confidence, and one weak
  word makes the whole line "read with low confidence", which would hide the states being demonstrated.

## Pre-flight checklist (run once the day before)

| Check | Command | Result when this guide was validated (2026-10-18, re-run after the newer features) |
|---|---|---|
| Backend tests | `cd backend` then `venv\Scripts\python.exe -m unittest discover -s tests -t .` (about 5 minutes) | 400 tests, OK |
| Frontend tests | `cd frontend` then `npm run test:logic` | 98 tests, all pass |
| Production build | `npm run build` | builds successfully |
| Demo account | register a fresh one; do not use a real person's account | - |
| Test image | `demo\synthetic_prescription.png` reads at 0.98 line confidence with Google Vision | 5 medicine lines, outcomes as in the table above |

If the numbers differ on the day, say so instead of quoting these.

## Where the project differs from the synopsis (say this before you are asked)

| Synopsis says | What the project actually does |
|---|---|
| "Real-Time Drug Price Comparison", "compare prices from multiple pharmacies" | Reference prices come from one community dataset snapshot (253,973 products). The app now has a **pharmacy-offers data model and a strict feed importer** (`backend/database/import_pharmacy_feed.py`), so prices a pharmacy reports are shown separately, with pharmacy, time and source. **No real pharmacy feed is connected**, so on a normal run the offers table is empty and the app says "No pharmacy has reported a price or stock". A dataset price is never shown as a pharmacy price |
| "Real-Time Drug Availability Tracking" | Availability appears only when a pharmacy has reported it (with its age; old reports are marked out of date). With no reports the app says it is not tracked. There is no live inventory connection |
| "Medicine Timeline" in the Smart Health Report | Implemented: a day-part timeline (morning / afternoon / evening / night) built from the dosing the reader found, on screen and in the PDF. Lines whose dosing could not be read are listed as "not read", never guessed. A possibly-misread schedule is marked "Possibly" |
| "AI-powered" report; "AI module (Gemini AI)" | The analysis is rule-based. The report summary uses Gemini **only if `GEMINI_API_KEY` is set**, sending only names, strengths, schedules and counts; every sentence is checked against the facts and a deterministic summary replaces it if the check fails. Without a key the deterministic summary is shown. "Explain this medicine" works the same way |
| "AI Confidence Score" | Shown per line, with the reasons, and the screen states what it means: how closely the text resembles a dataset product. It is a heuristic similarity score, not a calibrated probability, and a person's confirmation is what settles a line |
| OCR = EasyOCR | Google Cloud Vision is tried first and EasyOCR is the fallback, because EasyOCR could not read handwriting. The synopsis's slide 6 also lists Tesseract / Node / MongoDB, which does not match slides 4, 7 and 13 |
| "Scan medicines or prescriptions" | Both. **Scan** (menu) reads a photo of a pack and offers possible products. It is candidates only, never a confirmation; the photo is read once and deleted; nothing is stored. It cannot tell whether a pack is genuine |
| "Accuracy" (non-functional) | Not measured. There is no labelled test set yet |
| "Healthcare data sources" | Two real sources are registered and shown (About page and data-sources endpoint): the medicine dataset and the DDInter 2.0 interaction dataset, with their licences. Pharmacy feeds register themselves when imported |

## Showing the newer features

**Pharmacy offers (needs demo data; remove it afterwards).** The generator writes an invented feed; it is stored as `synthetic_demo` and labelled
"Demo data" everywhere.

```
python demo/make_demo_pharmacy_feed.py demo/demo_pharmacy_feed.csv
backend\venv\Scripts\python.exe backend/database/import_pharmacy_feed.py demo/demo_pharmacy_feed.csv --source-key demo_feed --name "Demo pharmacy feed" --kind synthetic_demo
```
Open Dolo 650 in a report or on the Medicines page: the detail lists four demo pharmacies (one out of stock, one out of date) beside, not
mixed into, the dataset reference price. When finished: `backend\venv\Scripts\python.exe backend/database/import_pharmacy_feed.py --remove-source demo_feed`.
Say plainly that these figures are invented for the demo.

**Medicine Timeline and report summary.** Upload the test page, open the report: the timeline sits above the table, the summary text
above it says how many lines are identified and which need checking. The same content is in the PDF.

**Alternatives.** In a matched line's detail, "How these were chosen" lists what the alternatives share (ingredients at the same strength,
dosage form, release type) and "Not compared" lists what the dataset cannot say. A line that still needs checking shows its alternatives
as information only and counts no saving.

**Scan.** Menu → Scan, upload a clear photo of a strip or box: ranked possible products, the text that was read, never a confirmation.
**Photo notes.** A blurred, dark or tiny photo gets warnings (not a block) so the person can retake it.
