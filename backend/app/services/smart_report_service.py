"""
Smart Health Report - the final module in the PPT pipeline.

Renders everything already computed for a prescription (OCR, Medicine
Detection, the Clinical Decision Engine, Price Comparison and Generic
Recommendation) into a single PDF the patient can keep or show to a
pharmacist.

This module computes NOTHING clinically new. It is a faithful presentation
layer over results the other modules produced, which is what keeps it honest:
if a medicine wasn't confidently identified, the report says so; if a price
wasn't available, the report says so rather than estimating. The data-source
and not-a-diagnosis disclaimers travel with the document, because a printed
page outlives the screen it came from.

It reads each line's status the same way the analysis page does (through
medicine_safety_service.annotate), so the two cannot disagree about whether a
line is matched, needs checking, or carries an allergy alert.
"""
import os
import re
from datetime import datetime
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    CondPageBreak, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from app.config import Config
from app.constants import DEMO_DISCLAIMER, PDF_FOOTER_NOTE
from app.models.medicine_model import get_prescription_medicines
from app.models.prescription_model import get_ocr_result_by_prescription
from app.services.price_comparison_service import get_annotated_price_comparison
from app.models.recommendation_model import get_recommendations
from app.models.safety_model import get_analysis_summary, get_findings
from app.models.user_model import get_user_allergies
from app.services import data_sources_service, data_validation_service, medicine_safety_service, offer_service, price_provenance_service, prescription_notes_service, recommendation_notes, report_summary_service, timeline_service
from app.services.display_rounding import percent, round_half_up
from app.services.match_status import is_confirmed
from app.services.release_type import RELEASE_LABELS

ACCENT = colors.HexColor("#1a50b8")
INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#e2e8f0")
ALERT_RED = colors.HexColor("#b91c1c")
SUCCESS_GREEN = colors.HexColor("#047857")
WARN_ORANGE = colors.HexColor("#c2410c")

PAGE_MARGIN = 16 * mm
CONTENT_WIDTH = A4[0] - 2 * PAGE_MARGIN  # 178 mm: every table is exactly this wide

# The engine's internal severity codes, written the way a patient reads them.
SEVERITY_LABELS = {
    "Major": "Major",
    "Moderate": "Moderate",
    "Minor": "Minor",
    "Unknown": "Unknown",
    "NEEDS_VERIFICATION": "Not checked",
}

ISSUE_TYPE_LABELS = {
    "interaction": "Drug interaction",
    "duplicate": "Duplicate medicine",
    "dosage_inconsistency": "Dosage inconsistency",
    "allergy_check": "Allergy check",
}

DISCLAIMER = (
    "PharmaCompare does not replace your doctor's prescription and does not diagnose. "
    "Alternatives are listed for price comparison only - never change, stop or start a "
    "medicine without confirming with your doctor or pharmacist."
)
PRICE_NOTE = (
    f"{DEMO_DISCLAIMER} They may not reflect what any specific pharmacy charges today."
)

_FILE_LIKE = re.compile(r"\.(png|jpe?g|pdf)$", re.IGNORECASE)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _is_printable(ch):
    try:
        ch.encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


def _esc(value):
    """
    Text that is safe to put inside a ReportLab Paragraph.

    Paragraph parses its text as markup, so an OCR line such as "Tab X <5 days"
    or "<i>" (unbalanced) made the whole report fail with a parse error, and a
    bare "&" or "<" in any medicine name or finding did the same. Every
    dynamic string goes through here before it is placed in a Paragraph.
    """
    text = _CONTROL_CHARS.sub("", "" if value is None else str(value)).replace("₹", "Rs ")
    # The built-in PDF font covers Latin-1 / Windows-1252 only. Anything else
    # (e.g. Devanagari or Chinese characters in an OCR line) would print as a
    # black box, so it is shown as "?" instead.
    text = "".join(ch if _is_printable(ch) else "?" for ch in text)
    return _xml_escape(text)


def _format_date(value):
    if hasattr(value, "strftime"):
        return f"{value.day} {value.strftime('%b %Y')}"
    return str(value or "-")


def prescription_title(prescription):
    """
    What the report calls the prescription. A name the user typed wins; a raw
    upload filename (or nothing) is never the identity - it becomes
    "Prescription - 5 Oct 2026", the same wording the app uses on screen.
    """
    name = (prescription.get("prescription_name") or "").strip()
    if name and not _FILE_LIKE.search(name):
        return name
    uploaded = prescription.get("upload_date")
    return f"Prescription — {_format_date(uploaded)}" if uploaded else "Prescription"


class _NumberedCanvas(rl_canvas.Canvas):
    """Canvas that can print "Page X of Y": the total is only known once every page exists."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_pages = []

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total):
        self.saveState()
        self.setFont("Helvetica", 7.5)
        self.setFillColor(MUTED)
        self.drawString(PAGE_MARGIN, 9 * mm, PDF_FOOTER_NOTE)
        self.drawRightString(A4[0] - PAGE_MARGIN, 9 * mm, f"Page {self._pageNumber} of {total}")
        self.restoreState()


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=20, textColor=INK, spaceAfter=2),
        "subtitle": ParagraphStyle("st", parent=base["Normal"], fontSize=9, textColor=MUTED, alignment=TA_CENTER, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=12, textColor=ACCENT, spaceBefore=12, spaceAfter=5),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9, textColor=INK, leading=13),
        "small": ParagraphStyle("s", parent=base["Normal"], fontSize=7.5, textColor=MUTED, leading=10),
        "cell": ParagraphStyle("c", parent=base["Normal"], fontSize=8, textColor=INK, leading=10.5),
        "cellmuted": ParagraphStyle("cm", parent=base["Normal"], fontSize=7.5, textColor=MUTED, leading=10),
        "cellwarn": ParagraphStyle("cw", parent=base["Normal"], fontSize=7.5, textColor=WARN_ORANGE, leading=10),
        "cellalert": ParagraphStyle("ca", parent=base["Normal"], fontSize=7.5, textColor=ALERT_RED, leading=10),
        "cellgood": ParagraphStyle("cg", parent=base["Normal"], fontSize=8, textColor=SUCCESS_GREEN, leading=10.5),
    }


def _heading(text, styles):
    """
    A section heading that is never stranded at the bottom of a page: if less than
    ~45 mm is left, start a new page first. (keepWithNext was tried and rejected - it
    glues the heading to the WHOLE following table, pushing a long table off page 1.)
    """
    return [CondPageBreak(45 * mm), Paragraph(text, styles["h2"])]


def _rupees(value):
    return f"Rs {float(value):.2f}" if value is not None else "-"


def _table(data, widths, extra_styles=()):
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), INK),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        *extra_styles,
    ]))
    return table


def _group_price_rows(price_rows):
    """Turns the flat Price_Comparison rows into {pm_id: {prescribed, alternatives}}."""
    grouped = {}
    for row in price_rows:
        entry = grouped.setdefault(row["pm_id"], {"prescribed": None, "alternatives": []})
        if row["row_type"] == "prescribed":
            entry["prescribed"] = row
        else:
            entry["alternatives"].append(row)
    for entry in grouped.values():
        entry["alternatives"].sort(key=lambda r: float(r["price"]))
    return grouped


def _status_for(pm, safety, identified):
    """The same words the analysis page uses in its Status column."""
    if pm["match_status"] == "user_unmatched":
        return "Entered by you" if safety.get("user_entered") else "Not identified (by you)"
    if not identified:
        return "Suggested" if safety.get("suggested") else "Needs verification"
    if pm["match_status"] == "user_confirmed":
        return "Confirmed"
    if safety["needs_disambiguation"] or safety["ocr_uncertain"] or safety.get("needs_check"):
        return "Check match"
    return "Matched"


def _confidence_text(pm, identified, safety=None):
    if pm["match_status"] == "user_confirmed":
        return "Confirmed by you"
    if pm["match_status"] == "user_unmatched":
        return "Entered by you" if safety and safety.get("user_entered") else "Marked by you"
    if not identified and safety and safety.get("needs_disambiguation"):
        # no single product was named, so there is no confidence to quote
        return f"{len(safety['match_options'])} possible products"
    confidence = pm.get("match_confidence")
    if confidence is None:
        return "No match found"
    pct = percent(confidence)
    return f"{pct}% confidence" if identified else f"Closest guess: {pct}%"


def _savings_for(identified, safety, entry):
    """
    (counts_toward_total, prescribed_price, alternative_row, saving, reason).

    A line counts toward the savings total only when it is identified, has a
    reliable reference price and a cheaper comparable alternative, is not
    waiting on a "check match" decision (the product shown may not be the one
    meant) and carries no allergy alert (we do not offer a substitute for a
    medicine the patient reported an allergy to).
    """
    if not identified:
        return False, None, None, None, "Not identified"
    if safety.get("brand_unspecified"):
        # The product on file is one of many with this composition: its price is not "the
        # prescribed price", so no saving is claimed against it.
        return False, None, None, None, "No brand named on the prescription"
    prescribed = entry["prescribed"] if entry else None
    price = float(prescribed["price"]) if prescribed and prescribed["price"] is not None else None
    if price is None or price <= 0:
        return False, None, None, None, "Price not available"
    if safety["allergy_alert"]:
        return False, price, None, None, "Not shown: allergy alert"
    if prescribed.get("price_flag"):
        return False, price, None, None, "Reference price looks unusual - not used for savings"
    alternatives = entry["alternatives"] if entry else []
    # The same eligibility the screen uses (price_quality.counts_for_savings): same pack
    # quantity, real price, no extreme-price flag, live and cheaper.
    comparable = [a for a in alternatives if a.get("counts_for_savings")]
    if not comparable:
        reason = "No cheaper same-pack match on file" if alternatives else "No cheaper match on file"
        return False, price, None, None, reason
    alt = min(comparable, key=lambda a: float(a["price"]))
    saving = price - float(alt["price"])
    if safety["needs_disambiguation"] or safety["ocr_uncertain"] or safety.get("needs_check"):
        return False, price, alt, saving, "Not counted: check match first"
    if safety.get("confirmed_with_conflicts"):
        return False, price, alt, saving, "Not counted: confirmed despite differences from the line"
    return True, price, alt, saving, None


def collect_report_data(prescription_id, prescription):
    """
    Gathers the stored results for one prescription and works out the
    savings total. Every figure here already exists in the database - this
    only selects and arranges it.
    """
    medicines = get_prescription_medicines(prescription_id)
    prices = _group_price_rows(get_annotated_price_comparison(prescription_id))

    # The patient's OWN saved allergies: the prescription's owner, not whoever
    # happens to be calling.
    owner_id = prescription.get("user_id")
    allergies = get_user_allergies(owner_id) if owner_id is not None else []
    ocr = get_ocr_result_by_prescription(prescription_id) or {}
    safety = medicine_safety_service.annotate(medicines, allergies, ocr.get("line_results") or [])

    lines = []
    total_saving = 0.0
    original_total = 0.0
    counted = 0
    for pm in medicines:
        identified = bool(is_confirmed(pm["match_status"]) and pm["medicine_id"])
        s = safety[pm["pm_id"]]
        counts, price, alt, saving, reason = _savings_for(identified, s, prices.get(pm["pm_id"]))
        if counts:
            total_saving += saving
            original_total += price
            counted += 1
        lines.append({
            "pm": pm, "safety": s, "identified": identified,
            "status": _status_for(pm, s, identified),
            "confidence": _confidence_text(pm, identified, s),
            "price": price, "alt": alt, "saving": saving if counts else None, "reason": reason,
        })

    needs_attention = sum(1 for ln in lines if ln["status"] in ("Needs verification", "Check match", "Suggested"))
    return {
        "prescription": prescription,
        "title": prescription_title(prescription),
        "lines": lines,
        # lines of the prescription that are not medicines, and what the allergy check had to work with
        "notes": prescription_notes_service.notes_from_ocr_lines(ocr.get("line_results") or []),
        # where the prices come from, and whether any live feed exists (the same statements the analysis page shows)
        "price_basis": price_provenance_service.dataset_basis(),
        "live_data": data_sources_service.live_data(),
        "allergy_check": medicine_safety_service.allergy_check_status(allergies),
        "timeline": timeline_service.build_timeline(timeline_service.entries_from_report_lines(lines)),
        # what pharmacies have reported for the identified medicines (empty when no feed has been imported)
        "offers": offer_service.offers_for_medicines([ln["pm"]["medicine_id"] for ln in lines if ln["identified"]]),
        "medicines": medicines,
        "prices": prices,
        "analysis": get_analysis_summary(prescription_id),
        "findings": get_findings(prescription_id),
        "recommendations": get_recommendations(prescription_id),
        "total_saving": round(total_saving, 2),
        "original_total": round(original_total, 2),
        "counted_for_savings": counted,
        "detected": len(lines),
        # identified and not waiting on a check; a line the person marked "not identified" is decided, but not settled
        "settled": sum(1 for ln in lines if ln["identified"] and ln["status"] not in ("Needs verification", "Check match", "Suggested")),
        "needs_attention": needs_attention,
    }


def _medicines_section(data, s):
    rows = [["Medicine", "Strength / form", "Dosage / frequency", "Match", "Status"]]
    for ln in data["lines"]:
        pm, sf = ln["pm"], ln["safety"]
        if ln["identified"]:
            cell = [Paragraph(f"<b>{_esc(pm['medicine_name'])}</b>", s["cell"])]
            raw = (pm["raw_text"] or "").strip()
            if raw and raw != pm["medicine_name"]:
                cell.append(Paragraph(f"Read as “{_esc(raw)}”", s["cellmuted"]))
            if pm.get("composition"):
                cell.append(Paragraph(f"Contains: {_esc(pm['composition'])}", s["cellmuted"]))
            if sf["brand_unspecified"]:
                cell.append(Paragraph("Generic name written: any brand with this composition fits.", s["cellmuted"]))
            for note in data_validation_service.data_notes(pm, warn_only=True):
                cell.append(Paragraph(f"Data note: {_esc(note['text'])}", s["cellmuted"]))
        elif sf.get("user_entered"):
            typed = sf["user_entered"]
            cell = [
                Paragraph(f"<b>{_esc(typed['name'])}</b>", s["cell"]),
                Paragraph(f"Entered by you. Read from the prescription as \u201c{_esc((pm['raw_text'] or '-').strip())}\u201d.", s["cellmuted"]),
                Paragraph("Not matched to the dataset: no price, saving or safety check is shown for it.", s["cellmuted"]),
            ]
        else:
            cell = [
                Paragraph(f"<b>{_esc(pm['raw_text'] or '-')}</b>", s["cell"]),
                Paragraph("Not confirmed - verify against the original prescription.", s["cellmuted"]),
            ]
            if sf.get("suggested"):
                cell.append(Paragraph(f"Suggested: {_esc(sf['suggestion']['medicine_name'])}. The name matches what was read; strength, form "
                                      "and the reading still need your check.", s["cellwarn"]))
            elif sf["closest_guesses"]:
                shown = "; ".join(f"{g['medicine_name']} ({percent(g['score'])}%)" for g in sf["closest_guesses"][:3] if g.get("medicine_name"))
                cell.append(Paragraph(f"Closest look-alikes (not confirmed): {_esc(shown)}", s["cellmuted"]))
            if not sf["needs_disambiguation"] and sf.get("verification_reasons"):
                cell.append(Paragraph(_esc(sf["verification_reasons"][0]), s["cellmuted"]))
            if sf["needs_disambiguation"]:
                if sf["verification_reason"]:
                    cell.append(Paragraph(_esc(sf["verification_reason"][0].upper() + sf["verification_reason"][1:] + "."), s["cellwarn"]))
                shown = [" ".join(x for x in (o.get("strength"), o.get("form")) if x) for o in sf["match_options"]]
                cell.append(Paragraph("Possible: " + _esc("; ".join(x for x in shown if x)), s["cellmuted"]))
        if sf["allergy_alert"]:
            cell.append(Paragraph(f"Allergy alert: {_esc(sf['allergy_alert_text'])}", s["cellalert"]))
        elif ln["identified"] and sf["verification_status"] == "flagged_for_review":
            cell.append(Paragraph(_esc(sf["verification_label"]), s["cellwarn"]))

        if ln["identified"]:
            strength_form = " ".join(x for x in (sf.get("display_strength") or pm["strength"], pm["form"]) if x) or "-"
            release = pm.get("release_type")
            if release:
                strength_form += f" ({RELEASE_LABELS.get(release, 'modified release')})"
        elif sf.get("user_entered"):
            strength_form = " ".join(x for x in (sf["user_entered"].get("strength"), sf["user_entered"].get("form")) if x) or "-"
        else:
            strength_form = "-"

        ins = sf.get("instructions") or {}
        dose_timing = ", ".join(x for x in (ins.get("dose"), ins.get("timing")) if x) or pm["dosage"]
        duration = f"for {ins['duration']}" if ins.get("duration") else (f"for {pm['duration']}" if pm["duration"] else None)
        if not duration and ins.get("duration_unreadable"):
            duration = "number of days not readable"
        instructions = " · ".join(
            p for p in (ins.get("text") or pm["frequency"], dose_timing, duration) if p
        ) or "Not specified"

        status_style = s["cellgood"] if ln["status"] in ("Matched", "Confirmed") else s["cellwarn"]
        rows.append([
            cell,
            Paragraph(_esc(strength_form), s["cell"]),
            Paragraph(_esc(instructions), s["cell"]),
            Paragraph(_esc(ln["confidence"]), s["cell"]),
            Paragraph(f"<b>{_esc(ln['status'])}</b>", status_style),
        ])
    return _table(rows, [56 * mm, 28 * mm, 38 * mm, 28 * mm, 28 * mm])


def _notes_section(data, s):
    """Instructions and notes on the prescription that are not medicines. Hindi text cannot be set in the PDF's font, so only its reading is."""
    flow = []
    for note in data["notes"]:
        if note["kind"] == "hindi_note":
            if note["possible_meaning"]:
                text = f"Handwritten Hindi note. Automatic reading, please check it: \u201c{note['possible_meaning']}\u201d. It does not say which medicine it belongs to."
            else:
                text = "A handwritten Hindi note that could not be translated automatically (see the original prescription)."
        else:
            text = note["text"]
        flow.append(Paragraph("\u2022 " + _esc(text), s["body"]))
    return flow


def _allergy_note(data, s):
    check = data["allergy_check"]
    return [Paragraph(f"<b>Allergy check:</b> {_esc(check['message'])}", s["body"] if check["declared"] else s["cellwarn"]), Spacer(1, 5)]


def _summary_section(data, s):
    """The plain-language summary and, always, who wrote it."""
    summary = report_summary_service.summarise(data)
    return [Paragraph(_esc(summary["text"]), s["body"]), Paragraph(f"<i>{_esc(summary['label'])}</i>", s["small"])]


def _alternatives_notes(s):
    """How the alternatives were chosen and what is not compared, in the same words as the screen."""
    notes = recommendation_notes.notes_for()
    return [
        Paragraph("<b>How alternatives are chosen:</b> a product with " + _esc("; ".join(notes["matched"])) + ".", s["small"]),
        Paragraph("<b>Not compared:</b> " + _esc("; ".join(notes["not_compared"])) + ".", s["small"]),
        Paragraph(_esc(notes["safety"] + " " + notes["ask_first"]), s["small"]),
    ]


def _offers_section(data, s):
    """What pharmacies have REPORTED (price, stock, when, which feed). Never mixed with the dataset's reference price."""
    rows = [["Medicine", "Pharmacy", "Price", "Stock", "Reported", "Source"]]
    demo = False
    for ln in data["lines"]:
        described = data["offers"].get(ln["pm"]["medicine_id"]) if ln["identified"] else None
        if not described:
            continue
        demo = demo or described["has_demo_data"]
        for i, item in enumerate(described["items"]):
            stock = "Stock not stated" if item["availability"] == "unknown" else item["availability_label"] + (" (old report)" if item["stock_stale"] else "")
            rows.append([
                Paragraph(_esc(ln["pm"]["medicine_name"]) if i == 0 else "", s["cell"]),
                Paragraph(_esc(item["pharmacy"] + (f", {item['city']}" if item["city"] else "")), s["cell"]),
                Paragraph(_esc(_rupees(item["price"]) + (" (old)" if item["price_stale"] else "") if item["price"] is not None else "No price"), s["cell"]),
                Paragraph(_esc(stock), s["cell"]),
                Paragraph(_esc(item["age"]), s["cell"]),
                Paragraph(_esc(item["source"] + (" (demo)" if item["demo"] else "")), s["cell"]),
            ])
    if len(rows) == 1:
        return [Paragraph("No pharmacy has reported a price or stock for the medicines on this prescription. " + _esc(data["live_data"]["statement"]), s["body"])]
    flow = []
    if demo:
        flow.append(Paragraph("<b>Demo data:</b> some of these are not real pharmacies and not real prices.", s["cellwarn"]))
    flow.append(_table(rows, [30 * mm, 36 * mm, 20 * mm, 32 * mm, 22 * mm, 38 * mm]))
    flow.append(Spacer(1, 3))
    flow.append(Paragraph("Reported by the pharmacies and not checked by PharmaCompare. Prices and stock change: confirm with the pharmacy.", s["small"]))
    return flow


def _timeline_section(data, s):
    """The Medicine Timeline: when each identified medicine is taken, exactly as the prescription wrote it."""
    timeline = data["timeline"]
    if not timeline["has_content"]:
        return [Paragraph("No dosing instructions could be read from this prescription.", s["body"])]
    rows = [["When", "Medicine", "Amount / timing", "How long"]]
    for slot in timeline["slots"]:
        for i, item in enumerate(slot["items"]):
            rows.append([
                Paragraph(f"<b>{_esc(slot['label'])}</b>" if i == 0 else "", s["cell"]),
                Paragraph(_esc(item["medicine"] or "-") + (" <i>(possible schedule)</i>" if item["possible"] else ""), s["cell"]),
                Paragraph(_esc(" · ".join(x for x in (item["amount"], item["timing"]) if x) or "-"), s["cell"]),
                Paragraph(_esc(item["duration"]), s["cell"]),
            ])
    for group in timeline["groups"]:
        for i, item in enumerate(group["items"]):
            rows.append([
                Paragraph(f"<b>{_esc(group['label'])}</b>" if i == 0 else "", s["cell"]),
                Paragraph(_esc(item["medicine"] or "-") + (" <i>(possible schedule)</i>" if item["possible"] else ""), s["cell"]),
                Paragraph(_esc(" · ".join(x for x in (item.get("frequency"), item["amount"], item["timing"]) if x) or "-"), s["cell"]),
                Paragraph(_esc(item["duration"]), s["cell"]),
            ])
    flow = [_table(rows, [28 * mm, 58 * mm, 52 * mm, 40 * mm]) if len(rows) > 1 else Spacer(1, 1)]
    if timeline["not_identified"]:
        flow.append(Spacer(1, 4))
        flow.append(Paragraph("<b>Not in the timeline until identified:</b> " + _esc("; ".join(
            f"“{n['source_text']}” read as {n['read_as'] or 'no schedule'}, {n['duration']}" for n in timeline["not_identified"])), s["small"]))
    flow.append(Spacer(1, 3))
    flow.append(Paragraph("Taken from the instructions written on the prescription. A schedule marked possible was only partly readable: "
                          "check the original. Nothing here is a dosing recommendation.", s["small"]))
    return flow


def _safety_section(data, s):
    flow = list(_allergy_note(data, s))
    analysis = data["analysis"]
    if analysis and analysis.get("summary"):
        flow.append(Paragraph(_esc(analysis["summary"]), s["body"]))
        flow.append(Spacer(1, 5))

    if not data["findings"]:
        flow.append(Paragraph("No drug-interaction findings were recorded for this prescription.", s["body"]))
        return flow

    rows = [["Type", "Severity", "Medicines", "What it means"]]
    for f in data["findings"]:
        involved = f.get("medicines_involved") or []
        names = " + ".join(m["medicine_name"] for m in involved) if involved else "-"
        issue_type = f["issue_type"] or ""
        rows.append([
            Paragraph(_esc(ISSUE_TYPE_LABELS.get(issue_type, issue_type.replace("_", " ").title())), s["cell"]),
            Paragraph(_esc(SEVERITY_LABELS.get(f["severity"], f["severity"] or "-")), s["cell"]),
            Paragraph(_esc(names), s["cell"]),
            Paragraph(_esc(f["explanation"] or "-"), s["cell"]),
        ])
    flow.append(_table(rows, [26 * mm, 20 * mm, 46 * mm, 86 * mm]))
    return flow


def _savings_section(data, s):
    flow = [
        Paragraph(f"<b>Where these prices come from.</b> {_esc(data['price_basis']['label'])} {_esc(data['live_data']['statement'])}", s["small"]),
        Spacer(1, 5),
    ]
    if data["total_saving"] > 0:
        pct = round_half_up(data["total_saving"] / data["original_total"] * 100) if data["original_total"] else 0
        flow.append(Paragraph(
            f"<b>Switching to the cheapest comparable alternative could save "
            f"{_rupees(data['total_saving'])} ({pct}% lower) across {data['counted_for_savings']} of "
            f"{data['detected']} medicine{'s' if data['detected'] != 1 else ''}.</b>",
            ParagraphStyle("sv", parent=s["body"], textColor=SUCCESS_GREEN, fontSize=10),
        ))
        flow.append(Paragraph(
            "Only medicines that are identified, have a reliable reference price, have a cheaper product with the same "
            "ingredients, strength and form, and are not waiting on a match check or an allergy alert are counted.",
            s["small"],
        ))
        flow.append(Spacer(1, 5))
    else:
        flow.append(Paragraph("No saving could be counted for this prescription.", s["body"]))
        flow.append(Spacer(1, 4))

    # One row for EVERY medicine: a line without a price or alternative says why,
    # instead of silently disappearing from the table.
    rows = [["Prescribed", "Reference price", "Cheapest comparable alternative", "Alt. price", "You could save"]]
    for ln in data["lines"]:
        pm = ln["pm"]
        name = pm["medicine_name"] if ln["identified"] else (pm["raw_text"] or "-")
        alt = ln["alt"]
        if ln["saving"] is not None:
            save_cell = Paragraph(_esc(_rupees(ln["saving"])), s["cellgood"])
        else:
            save_cell = Paragraph(_esc(ln["reason"] or "-"), s["cellmuted"])
        rows.append([
            Paragraph(_esc(name), s["cell"]),
            Paragraph(_esc(_rupees(ln["price"])), s["cell"]),
            Paragraph(_esc(alt["medicine_name"]) if alt and ln["reason"] != "Not shown: allergy alert" else "-", s["cell"]),
            Paragraph(_esc(_rupees(alt["price"])) if alt and ln["reason"] != "Not shown: allergy alert" else "-", s["cell"]),
            save_cell,
        ])
    flow.append(_table(rows, [46 * mm, 24 * mm, 52 * mm, 20 * mm, 36 * mm]))
    flow.append(Spacer(1, 4))
    flow.append(Paragraph(_esc(PRICE_NOTE), s["small"]))
    return flow


def build_report_pdf(prescription_id, prescription, output_path):
    """Renders the report to output_path and returns that path."""
    data = collect_report_data(prescription_id, prescription)
    s = _styles()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN, topMargin=PAGE_MARGIN, bottomMargin=18 * mm,
        title="PharmaCompare Smart Health Report",
    )

    summary = f"{data['detected']} detected · {data['settled']} matched or confirmed · {data['needs_attention']} need checking"
    flow = [
        Paragraph("Smart Health Report", s["title"]),
        Paragraph("Generated by PharmaCompare", s["subtitle"]),
        _table(
            [[Paragraph("<b>Prescription</b>", s["cell"]), Paragraph(_esc(data["title"]), s["cell"]),
              Paragraph("<b>Uploaded</b>", s["cell"]), Paragraph(_esc(_format_date(prescription.get("upload_date"))), s["cell"])],
             [Paragraph("<b>Medicines</b>", s["cell"]), Paragraph(_esc(summary), s["cell"]),
              Paragraph("<b>Report generated</b>", s["cell"]), Paragraph(datetime.now().strftime("%d %b %Y, %I:%M %p"), s["cell"])]],
            [28 * mm, 64 * mm, 32 * mm, 54 * mm],
        ),
        *_heading("Summary", s),
        *_summary_section(data, s),
        *_heading("Doctor prescribed medicines", s),
        _medicines_section(data, s),
        *([*_heading("Other instructions on the prescription (not medicines)", s), *_notes_section(data, s)] if data["notes"] else []),
        *_heading("Medicine timeline", s),
        *_timeline_section(data, s),
        *_heading("Safety check", s),
        *_safety_section(data, s),
        *_heading("Price comparison &amp; possible savings", s),
        *_savings_section(data, s),
        *_alternatives_notes(s),
        *_heading("Pharmacy prices and stock (as reported)", s),
        *_offers_section(data, s),
        Spacer(1, 14),
    ]
    flow.append(KeepTogether([
        _table([[Paragraph(f"<b>Important:</b> {_esc(DISCLAIMER)}", s["small"])]], [CONTENT_WIDTH],
               extra_styles=[("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbeb"))]),
    ]))

    doc.build(flow, canvasmaker=_NumberedCanvas)
    return output_path


def report_path_for(prescription_id, user_id):
    return os.path.join(Config.UPLOAD_FOLDER, "reports", str(user_id),
                        f"smart_report_{prescription_id}.pdf")
