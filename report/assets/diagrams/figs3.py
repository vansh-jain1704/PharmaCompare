"""Chapter 3 diagrams for the CURRENT implementation (16 tables, scan, timeline, notes, offers)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_figs as M
from make_figs import *

M.OUT = sys.argv[1]


# ---------------------------------------------------------------- Fig 3.1 architecture
def fig_arch3():
    fig, ax = new(7.4, 6.0, (0, 100), (-14, 82))
    box(ax, 6, 44, 10, 10, "User", fc=C_GREY, fs=11, bold=True)
    box(ax, 24, 44, 18, 13, "React.js\nfront end", fc=C_BLUE, fs=10.5)
    box(ax, 53, 44, 28, 15, "Flask REST API\nauthentication and\nservice coordination", fc=C_GREEN, fs=10)
    box(ax, 53, 71, 28, 12, "OCR engine\nGoogle Cloud Vision,\nEasyOCR as fallback", fc=C_PURP, fs=10)
    box(ax, 86, 44, 22, 20, "MySQL database\n16 tables, with the\nmedicine table and\ninteraction pairs", fc=C_PURP, fs=9.4)
    box(ax, 86, 71, 22, 12, "Gemini\n(optional, wording\nof summaries only)", fc=C_GREY, fs=9)
    box(ax, 53, 15, 56, 24, "", fc=C_YEL)
    ax.text(53, 24.6, "Clinical decision engine", ha="center", va="center", fontsize=10.8, fontweight="bold", zorder=4)
    ax.text(53, 12.6, "Medicine matching and match status\nDosing reading and medicine timeline\nInteraction, duplicate and allergy check\nPrice comparison and cheaper alternatives\nUser verification and audit trail",
            ha="center", va="center", fontsize=9.2, zorder=4, linespacing=1.4)
    box(ax, 53, -9, 56, 9, "Smart Health Report (PDF)\ntimeline, safety alerts, savings, recommendations", fc=C_BLUE, fs=9.2)
    arrow(ax, (11, 44), (15, 44), both=True)
    arrow(ax, (33, 44), (39, 44), both=True)
    ax.text(36, 52.5, "HTTPS\nJSON", ha="center", va="center", fontsize=8.2, style="italic")
    arrow(ax, (53, 51.5), (53, 65), both=True)
    arrow(ax, (67, 44), (75, 44), both=True)
    arrow(ax, (53, 36.5), (53, 27), both=True)
    arrow(ax, (63, 51.5), (77, 65.5), dash=True)
    arrow(ax, (84, 34), (75, 27), both=True, dash=True)
    arrow(ax, (53, 3), (53, -4.5))
    save(fig, "fig3_1_architecture.png")


# ---------------------------------------------------------------- Fig 3.2 ER (16 tables)
def fig_er3():
    W = 28.5
    cols = [15.5, 50, 84.5]
    tables = {
        "Users": ["user_id (PK)", "name, email (unique)", "phone, password (hash)", "allergies (JSON)", "created_at"],
        "Prescriptions": ["prescription_id (PK)", "user_id (FK)", "image_path, prescription_name", "prescription_type, symptoms", "upload_date, status"],
        "OCR_Results": ["ocr_id (PK)", "prescription_id (FK)", "extracted_text", "line_results (JSON)", "confidence_score"],
        "AI_Analysis": ["analysis_id (PK)", "prescription_id (FK)", "summary", "risk_level", "analysis_date"],
        "Prescription_Medicines": ["pm_id (PK)", "prescription_id (FK)", "medicine_id (FK, null)", "dosage, frequency, duration", "raw_text, match_confidence", "match_status, match_options"],
        "Safety_Findings": ["finding_id (PK)", "prescription_id (FK)", "issue_type, severity", "medicines_involved (JSON)", "confidence, explanation", "recommendation, data_source"],
        "Price_Comparison": ["price_id (PK)", "pm_id, medicine_id (FK)", "row_type, price", "price_per_unit, pack_size", "savings_percent", "price_date"],
        "Medicines": ["medicine_id (PK)", "medicine_name, composition", "primary_salt, secondary_salt", "form, strength", "release_type, pack_size", "price, is_discontinued", "composition_incomplete", "manufacturer, data_source"],
        "Generic_Recommendations": ["gr_id (PK)", "pm_id (FK)", "recommended_medicine_id (FK)", "price_difference", "confidence_score, reason"],
        "Drug_Interactions": ["interaction_id (PK)", "drug_a, drug_b", "drug_a_norm, drug_b_norm", "severity, data_source"],
        "Pharmacy_Offers": ["offer_id (PK)", "pharmacy_id (FK)", "medicine_id (FK)", "price, availability", "quantity_available", "observed_at, imported_at"],
        "Smart_Health_Report": ["report_id (PK)", "prescription_id (FK)", "report_file", "generated_date"],
        "Data_Sources": ["source_id (PK)", "source_key (unique)", "name, kind, url", "license, record_count", "retrieved_at, notes"],
        "Pharmacies": ["pharmacy_id (PK)", "name, city, address", "source_id (FK)", "created_at"],
        "System_Logs": ["log_id (PK)", "user_id (FK, null)", "action (audit)", "timestamp, details"],
        "Partner_Keys": ["key_id (PK)", "source_id (FK)", "label, key_prefix", "key_hash (unique)", "last_used_at, revoked_at"],
    }
    grid = [["Users", "Prescriptions", "OCR_Results"],
            ["AI_Analysis", "Prescription_Medicines", "Safety_Findings"],
            ["Price_Comparison", "Medicines", "Generic_Recommendations"],
            ["Drug_Interactions", "Pharmacy_Offers", "Smart_Health_Report"],
            ["Data_Sources", "Pharmacies", "System_Logs"],
            ["Partner_Keys", None, None]]
    lh, hh, gap = 2.75, 4.4, 10
    pos = {}
    top = 0
    for row in grid:
        rh = max(hh + lh * len(tables[n]) for n in row if n)
        for c, n in zip(cols, row):
            if n:
                pos[n] = (c, top, hh + lh * len(tables[n]))
        top -= rh + gap
    fig, ax = new(7.6, 7.6 * (3 - (top + gap - 1)) / 100, (0, 100), (top + gap - 1, 3))
    for n, (cx, tp, h) in pos.items():
        ax.add_patch(Rectangle((cx - W / 2, tp - h), W, h, fc=C_PURP, ec=EDGE, lw=1.3, zorder=2))
        ax.add_patch(Rectangle((cx - W / 2, tp - hh), W, hh, fc="#cfd9e8", ec=EDGE, lw=1.3, zorder=3))
        ax.text(cx, tp - hh / 2, n, ha="center", va="center", fontsize=8.9, fontweight="bold", zorder=4)
        for i, f in enumerate(tables[n]):
            ax.text(cx - W / 2 + 1.0, tp - hh - lh * (i + 0.62), f, ha="left", va="center", fontsize=7.7, zorder=4)
    L = lambda n: (pos[n][0] - W / 2, pos[n][1] - pos[n][2] / 2)
    R = lambda n: (pos[n][0] + W / 2, pos[n][1] - pos[n][2] / 2)
    T = lambda n, dx=0: (pos[n][0] + dx, pos[n][1])
    B = lambda n, dx=0: (pos[n][0] + dx, pos[n][1] - pos[n][2])
    lab = lambda p, q, t, **k: arrow(ax, p, q, text=t, fs=7.6, **k)
    yUP = pos["Users"][1] - pos["Users"][2] / 2
    lab((R("Users")[0], yUP), (L("Prescriptions")[0], yUP), "1 : N", off=(0, 2.2))
    lab((R("Prescriptions")[0], yUP), (L("OCR_Results")[0], yUP), "1 : 1*", off=(0, 2.2))
    lab(B("Prescriptions"), T("Prescription_Medicines"), "1 : N", off=(4.5, 0))
    lab(B("Prescriptions", -9), T("AI_Analysis", 7), "1 : N", off=(-2, 1))
    lab(B("Prescriptions", 9), T("Safety_Findings", -7), "1 : N", off=(2, 1))
    lab(B("Prescription_Medicines"), T("Medicines"), "N : 1", off=(4.5, 0))
    lab(B("Prescription_Medicines", -9), T("Price_Comparison", 7), "1 : N", off=(-2, 1))
    lab(B("Prescription_Medicines", 9), T("Generic_Recommendations", -7), "1 : N", off=(2, 1))
    lab(B("Medicines", -4), T("Drug_Interactions", 7), "by ingredient name", dash=True, off=(-1, 1.5))
    lab(T("Pharmacy_Offers"), B("Medicines"), "N : 1", off=(4.5, 0))
    lab(B("Pharmacy_Offers"), T("Pharmacies"), "N : 1", off=(4.5, 0))
    lab(L("Pharmacies"), R("Data_Sources"), "N : 1", off=(0, 2.2))
    lab(B("Data_Sources"), T("Partner_Keys"), "1 : N", off=(4.5, 0))
    ax.text(50, top + gap - 0.5, "Dashed link: no foreign key (matched by ingredient name). * One OCR row per upload by application logic; not enforced by a unique key.\n"
            "Not drawn: System_Logs.user_id (FK to Users) and Smart_Health_Report.prescription_id (FK to Prescriptions).",
            ha="center", va="top", fontsize=7.8, style="italic")
    save(fig, "fig3_2_er_diagram.png")


# ---------------------------------------------------------------- Fig 3.3 sequence
def fig_seq3():
    fig, ax = new(7.8, 7.8, (0, 104), (0, 106))
    names = ["User", "React\nfrontend", "Flask API", "OCR engine", "Back-end\nservices", "MySQL"]
    xs = [9, 26, 44, 62, 80, 95]
    top = 102
    for n, x in zip(names, xs):
        box(ax, x, top, 15, 6.0, n, fc=C_BLUE, fs=8.2, bold=True)
        ax.plot([x, x], [top - 3.4, 1.5], color="#777777", lw=1, ls=(0, (5, 3)), zorder=0)
    msgs = [
        (0, 1, "1  Log in", False), (1, 2, "2  POST /api/auth/login", False),
        (2, 5, "3  Read user, check password hash", False), (2, 1, "4  JWT access token", True),
        (0, 1, "5  Choose prescription file", False), (1, 2, "6  POST /api/prescriptions/upload", False),
        (2, 5, "7  Save file, INSERT Prescriptions", False), (2, 3, "8  Image (or page 1 of PDF)", False),
        (3, 2, "9  Words, boxes, confidences", True), (2, 2, "10  Group lines; readable? photo checks", False),
        (2, 5, "11  INSERT OCR_Results", False), (2, 4, "12  Match; safety; prices; timeline", False),
        (4, 5, "13  Read Medicines, Drug_Interactions", False), (4, 5, "14  INSERT lines, findings, prices", False),
        (2, 1, "15  Result (lines, status, analysis)", True), (0, 1, "16  Choose a product for a line", False),
        (1, 2, "17  PATCH .../medicines/{pm_id}", False), (2, 1, "18  409 warnings if the line conflicts", True),
        (1, 2, "19  PATCH again, acknowledge_warnings", False), (2, 5, "20  Save choice; INSERT System_Logs", False),
        (2, 4, "21  Re-run safety, prices, alternatives", False), (2, 1, "22  Updated analysis", True),
        (0, 1, "23  Download report", False), (1, 2, "24  GET .../report (PDF built, row saved)", False),
        (2, 0, "25  Smart Health Report (PDF)", True),
    ]
    step = 3.75
    y = top - 7.5
    for s_, d_, label, ret in msgs:
        if s_ == d_:
            x = xs[s_]
            ax.add_patch(Rectangle((x - 0.8, y - 1.4), 1.6, 2.8, fc="white", ec=EDGE, lw=1, zorder=3))
            ax.text(x + 2.4, y, label, ha="left", va="center", fontsize=7.4, zorder=5, bbox=dict(fc="white", ec="none", pad=0.3))
            y -= step * 0.55
        else:
            arrow(ax, (xs[s_], y), (xs[d_], y), dash=ret)
            lo, hi = sorted((xs[s_], xs[d_]))
            ax.text((lo + hi) / 2, y + 0.9, label, ha="center", va="bottom", fontsize=7.4, zorder=5, bbox=dict(fc="white", ec="none", pad=0.3))
        y -= step
    save(fig, "fig3_3_sequence.png")


# ---------------------------------------------------------------- Fig 3.5 DFD level 1
def fig_dfd1b():
    fig, ax = new(7.6, 8.2, (0, 100), (0, 120))
    box(ax, 10, 102, 17, 10, "User", fc=C_GREY, fs=11, bold=True, rounded=False)
    procs = [("1.0\nCapture and\nextract (OCR)", 38, 108), ("2.0\nDetect and\nconfirm medicines", 38, 84), ("3.0\nAnalyze\nsafety", 38, 60),
             ("4.0\nCompare prices,\nrecommend", 38, 36), ("5.0\nGenerate\nreport", 38, 12)]
    for t, x, y in procs:
        ax.add_patch(Ellipse((x, y), 26, 15.5, fc=C_BLUE, ec=EDGE, lw=1.4, zorder=2))
        ax.text(x, y, t, ha="center", va="center", fontsize=8.8, zorder=3, linespacing=1.15)

    def store(x, y, w, label):
        ax.plot([x - w / 2, x + w / 2], [y + 3.2, y + 3.2], color=EDGE, lw=1.4)
        ax.plot([x - w / 2, x + w / 2], [y - 3.2, y - 3.2], color=EDGE, lw=1.4)
        ax.plot([x - w / 2, x - w / 2], [y - 3.2, y + 3.2], color=EDGE, lw=1.4)
        ax.plot([x + w / 2, x + w / 2], [y - 3.2, y + 3.2], color=EDGE, lw=1.4)
        ax.text(x + 0.8, y, label, ha="center", va="center", fontsize=8.2)
    store(82, 108, 28, "D1  Prescriptions + OCR")
    store(82, 92, 28, "D2  Medicines (reference)")
    store(82, 76, 28, "D3  Lines + status + audit log")
    store(82, 60, 28, "D4  Drug_Interactions")
    store(82, 46, 28, "D5  Analysis + findings")
    store(82, 32, 28, "D6  Prices + recommendations")
    store(82, 22, 28, "D7  Pharmacy offers + sources")
    store(82, 12, 28, "D8  Smart_Health_Report")
    box(ax, 10, 22, 17, 9, "Smart Health\nReport", fc=C_GREY, fs=9, rounded=False)
    a = lambda p, q, lab=None, **k: arrow(ax, p, q, text=lab, fs=7.8, **k)
    a((18.5, 104), (25, 108.5), "Prescription\nfile", off=(-3, 5))
    a((38, 100.2), (38, 91.8), "Text lines +\nconfidence", off=(9.5, 0))
    a((51, 108), (68, 108), None, both=True)
    a((51, 84), (68, 92), "Candidates", off=(-1, 3.2), both=True)
    a((51, 82), (68, 76.5), "Lines + status", off=(-1, -3.2))
    a((18.5, 99), (25, 82), "Confirm /\nchoose", off=(-6, 4))
    a((38, 76.2), (38, 67.8), "Confirmed\nlines", off=(9, 0))
    a((51, 60), (68, 60), None, both=True)
    a((51, 58), (68, 46.5), "Findings", off=(-1, -3))
    a((38, 52.2), (38, 43.8), "Confirmed\nlines", off=(9, 0))
    a((51, 36), (68, 32.5), "Prices,\nalternatives", off=(-2, 3.5))
    a((51, 33), (68, 23), None, both=True)
    a((38, 28.2), (38, 19.8), "Findings, prices,\nalternatives", off=(-12, 0))
    a((51, 12), (68, 12), "PDF", off=(0, 2.5))
    a((25, 14), (18.5, 20), None)
    save(fig, "fig3_5_dfd1.png")


# ---------------------------------------------------------------- Fig 3.6 flow chart
def fig_flow3():
    fig, ax = new(6.4, 9.4, (0, 100), (-22, 176))
    X = 38

    def b(y, t, fc=C_BLUE, w=56, h=7.5): box(ax, X, y, w, h, t, fc=fc, fs=9.2)
    box(ax, X, 172, 24, 6, "START", fc=C_GREEN, fs=10, bold=True)
    b(161, "User registers / logs in")
    b(150, "Upload prescription (JPG, PNG or PDF)")
    b(139, "Photo-quality notes; OCR (Google Vision or\nEasyOCR); text grouped into lines", h=9)
    diamond(ax, X, 123, 46, 14, "Page readable?\n(mean confidence >= 0.35)")
    box(ax, 88, 123, 20, 10, "Ask user to\nre-upload", fc=C_RED, fs=9)
    arrow(ax, (X + 23, 123), (78, 123), "No", off=(0, 2)); arrow(ax, (88, 128), (88, 150), None); arrow(ax, (88, 150), (X + 28, 150), None)
    b(107, "Each line matched to the medicine dataset;\ndosing instructions read", h=9)
    diamond(ax, X, 91, 48, 14, "Line settled automatically?\n(score + identity evidence)")
    box(ax, 88, 91, 20, 12, "needs_verification:\nuser picks, searches,\nenters or rejects", fc=C_RED, fs=8.2)
    arrow(ax, (X + 24, 91), (78, 91), "No", off=(0, 2.2))
    b(75, "Confirmed lines only\n(matched or user confirmed)", h=9)
    arrow(ax, (88, 85), (88, 75), None); arrow(ax, (88, 75), (X + 28, 75), "user confirms\n(warnings shown)", off=(2, -5.5))
    diamond(ax, X, 60, 50, 14, "Interaction, duplicate or\nallergy risk found?")
    box(ax, 88, 60, 20, 9, "Display safety\nalert", fc=C_RED, fs=9)
    arrow(ax, (X + 25, 60), (78, 60), "Yes", off=(0, 2.2))
    b(44, "Medicine price comparison\n(same composition, strength and form)", h=9)
    b(32, "Cheaper-alternative recommendation\n(up to three, with reasons)", h=9)
    b(21, "Medicine timeline from the written dosing")
    b(10, "Generate Smart Health Report")
    b(-1, "View / download PDF report")
    box(ax, X, -12, 24, 6, "END", fc=C_GREEN, fs=10, bold=True)
    arrow(ax, (X, 169), (X, 164.8)); arrow(ax, (X, 157.2), (X, 153.8)); arrow(ax, (X, 146.2), (X, 143.6)); arrow(ax, (X, 134.4), (X, 130.0))
    arrow(ax, (X, 116), (X, 111.6), "Yes", off=(5, 0)); arrow(ax, (X, 102.4), (X, 98.0))
    arrow(ax, (X, 84), (X, 79.6), "Yes", off=(5, 0)); arrow(ax, (X, 70.4), (X, 67.0))
    arrow(ax, (88, 55.5), (88, 51)); arrow(ax, (88, 51), (X + 28, 51), "continue", off=(0, 2))
    arrow(ax, (X, 53), (X, 48.6), "No", off=(5, 0))
    arrow(ax, (X, 39.4), (X, 36.6)); arrow(ax, (X, 27.4), (X, 24.8)); arrow(ax, (X, 17.2), (X, 13.8)); arrow(ax, (X, 6.2), (X, 2.8))
    arrow(ax, (X, -4.8), (X, -9.0))
    save(fig, "fig3_6_flowchart.png")


if __name__ == "__main__":
    fig_arch3(); fig_er3(); fig_seq3(); fig_dfd1b(); fig_flow3()



