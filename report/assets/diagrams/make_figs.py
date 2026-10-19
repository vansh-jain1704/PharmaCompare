"""Diagrams for the PharmaCompare project report (matplotlib only)."""
import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle, FancyArrowPatch, Ellipse
from matplotlib import font_manager

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
for f in ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"):
    p = os.path.join(r"C:\Windows\Fonts", f)
    if os.path.exists(p):
        font_manager.fontManager.addfont(p)
plt.rcParams["font.family"] = "Times New Roman"
plt.rcParams["font.size"] = 10

C_BLUE, C_GREEN, C_YEL, C_PURP, C_RED, C_GREY = "#e3ecf8", "#e5f1e6", "#fdf3d8", "#ece4f3", "#f8dfdb", "#eeeeee"
EDGE = "#222222"


def new(w, h, xlim, ylim):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(*xlim); ax.set_ylim(*ylim); ax.axis("off")
    return fig, ax


def box(ax, cx, cy, w, h, text, fc=C_BLUE, fs=10, bold=False, rounded=True, lw=1.4, ec=EDGE):
    st = "round,pad=0.02,rounding_size=1.2" if rounded else "square,pad=0"
    p = FancyBboxPatch((cx - w / 2, cy - h / 2), w, h, boxstyle=st, fc=fc, ec=ec, lw=lw, zorder=2)
    ax.add_patch(p)
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, fontweight="bold" if bold else "normal", zorder=3, linespacing=1.2)


def diamond(ax, cx, cy, w, h, text, fc=C_YEL, fs=9.5):
    ax.add_patch(Polygon([(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)], fc=fc, ec=EDGE, lw=1.4, zorder=2))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, zorder=3, linespacing=1.15)


def arrow(ax, p1, p2, text=None, both=False, dash=False, fs=9, off=(0, 0), rad=0.0, ha="center", color=EDGE):
    style = "<|-|>" if both else "-|>"
    a = FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=11, lw=1.3, color=color, zorder=1,
                        linestyle=(0, (4, 3)) if dash else "-", connectionstyle=f"arc3,rad={rad}", shrinkA=0, shrinkB=0)
    ax.add_patch(a)
    if text:
        mx, my = (p1[0] + p2[0]) / 2 + off[0], (p1[1] + p2[1]) / 2 + off[1]
        ax.text(mx, my, text, ha=ha, va="center", fontsize=fs, style="italic", zorder=4,
                bbox=dict(fc="white", ec="none", pad=0.8))


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), dpi=200, bbox_inches="tight", pad_inches=0.12, facecolor="white")
    plt.close(fig)
    print("saved", name)


# ---------------------------------------------------------------- Fig 2.1 project cycle
def fig_cycle():
    fig, ax = new(7.4, 4.4, (0, 100), (-6, 62))
    stages = [
        ("Domain\nselection", "Feb 2026"),
        ("Problem statement,\nliterature survey", "Mar 2026"),
        ("Objectives\nidentification", "Apr 2026"),
        ("SRS: architecture,\nDFD, use cases", "May-Jun 2026"),
        ("Phase-II review", "Aug 2026"),
        ("Implementation\n(React, Flask, MySQL)", "Aug-Oct 2026"),
        ("Testing\n(206 + 28 tests)", "Oct 2026"),
        ("Results and\nreport writing", "Oct 2026"),
    ]
    xs = [12, 37, 62, 87]
    pos = []
    for i, (t, d) in enumerate(stages):
        row = 0 if i < 4 else 1
        x = xs[i] if row == 0 else xs[7 - i]
        y = 47 if row == 0 else 17
        fc = C_BLUE if i < 5 else C_GREEN
        box(ax, x, y, 22, 17, t, fc=fc, fs=9.3)
        ax.text(x, y - 6.0, d, ha="center", va="center", fontsize=8.6, style="italic", zorder=4)
        ax.text(x, y + 3.2, t, ha="center", va="center", fontsize=9.3, zorder=5, linespacing=1.2) if False else None
        pos.append((x, y))
    for i in range(3):
        arrow(ax, (pos[i][0] + 11.8, pos[i][1]), (pos[i + 1][0] - 11.8, pos[i + 1][1]))
    arrow(ax, (pos[3][0], pos[3][1] - 8.8), (pos[4][0], pos[4][1] + 8.8))
    for i in range(4, 7):
        arrow(ax, (pos[i][0] - 11.8, pos[i][1]), (pos[i + 1][0] + 11.8, pos[i + 1][1]))
    # feedback loop: testing -> implementation (drawn below the bottom row)
    ax.plot([pos[6][0], pos[6][0]], [pos[6][1] - 8.8, -1.5], color=EDGE, lw=1.3, ls=(0, (4, 3)))
    ax.plot([pos[6][0], pos[5][0]], [-1.5, -1.5], color=EDGE, lw=1.3, ls=(0, (4, 3)))
    arrow(ax, (pos[5][0], -1.5), (pos[5][0], pos[5][1] - 8.8), dash=True)
    ax.text((pos[6][0] + pos[5][0]) / 2, -4.2, "failed tests are fixed in the implementation", ha="center", fontsize=8.6, style="italic")
    save(fig, "fig2_1_project_cycle.png")


# ---------------------------------------------------------------- Fig 3.1 architecture
def fig_arch():
    fig, ax = new(7.4, 8.6, (0, 100), (-16, 106))
    box(ax, 50, 101, 40, 7, "User (web browser)", fc=C_GREY, fs=11, bold=True)
    box(ax, 50, 87, 92, 11, "Presentation layer\nReact 19 + Vite single-page application\nRegister, onboarding, upload, verification, report, search, profile", fc=C_BLUE, fs=10)
    box(ax, 50, 70, 92, 11, "Application layer: Flask REST API (blueprints)\nJWT authentication, password hashing, input validation, file checks", fc=C_GREEN, fs=10)
    arrow(ax, (50, 97.5), (50, 92.6), both=True)
    arrow(ax, (50, 81.4), (50, 75.6), both=True, text="HTTPS / JSON", off=(10, 0))
    # services row
    sy = 49
    items = [("OCR service\nline grouping,\nreadability gate", 17), ("Medicine matching\nand match status", 50), ("Clinical decision\nengine: interactions,\nduplicates, allergy", 83)]
    for t, x in items:
        box(ax, x, sy, 28, 14, t, fc=C_YEL, fs=9.5)
        arrow(ax, (x, 64.4), (x, sy + 7.2))
    arrow(ax, (31.2, sy), (35.8, sy)); arrow(ax, (64.2, sy), (68.8, sy))
    sy2 = 29
    items2 = [("Smart Health Report\n(PDF, ReportLab)", 17), ("Generic / cheaper\nalternatives", 50), ("Price comparison and\nprice-quality flags", 83)]
    for t, x in items2:
        box(ax, x, sy2, 28, 12, t, fc=C_YEL, fs=9.5)
    arrow(ax, (83, sy - 7.2), (83, sy2 + 6.2))
    arrow(ax, (68.8, sy2), (64.2, sy2)); arrow(ax, (35.8, sy2), (31.2, sy2))
    # data
    box(ax, 28, 10, 50, 11, "MySQL database (12 tables)\nUsers, Prescriptions, OCR_Results, Medicines,\nPrescription_Medicines, findings, prices, reports", fc=C_PURP, fs=9)
    box(ax, 80, 10, 36, 11, "Reference data (static)\n253,973 medicine products\nDDInter 2.0 interaction pairs", fc=C_PURP, fs=9)
    for x in (17, 50):
        arrow(ax, (x, sy2 - 6.2), (min(max(x, 12), 44), 15.7), both=True, dash=True)
    arrow(ax, (83, sy2 - 6.2), (80, 15.7), both=True, dash=True)
    # external
    ax.text(50, -1.5, "External services (used only by the OCR service and the optional explainer)", ha="center", fontsize=9, style="italic")
    for t, x in [("Google Cloud Vision\n(primary OCR engine)", 17), ("EasyOCR (local\nfallback engine)", 50), ("Gemini API (optional,\nmedicine explanations)", 83)]:
        box(ax, x, -10, 28, 8, t, fc=C_GREY, fs=9)
    save(fig, "fig3_1_architecture.png")


# ---------------------------------------------------------------- Fig 3.2 ER
def fig_er():
    fig, ax = new(7.6, 8.6, (0, 100), (0, 112))
    def table(cx, top, w, name, fields, fc=C_PURP):
        lh = 3.5
        h = 5.2 + lh * len(fields)
        ax.add_patch(Rectangle((cx - w / 2, top - h), w, h, fc=fc, ec=EDGE, lw=1.3, zorder=2))
        ax.add_patch(Rectangle((cx - w / 2, top - 5.2), w, 5.2, fc="#cfd9e8", ec=EDGE, lw=1.3, zorder=3))
        ax.text(cx, top - 2.6, name, ha="center", va="center", fontsize=9.6, fontweight="bold", zorder=4)
        for i, f in enumerate(fields):
            ax.text(cx - w / 2 + 1.2, top - 5.2 - lh * (i + 0.6), f, ha="left", va="center", fontsize=7.9, zorder=4)
        return (cx, top, w, h)
    t = {}
    t["Users"] = table(14, 110, 25, "Users", ["user_id (PK)", "name, email (unique)", "phone, password (hash)", "allergies (JSON)", "created_at"])
    t["Prescriptions"] = table(50, 110, 27, "Prescriptions", ["prescription_id (PK)", "user_id (FK)", "image_path, prescription_name", "prescription_type, symptoms", "upload_date, status"])
    t["OCR"] = table(86, 110, 25, "OCR_Results", ["ocr_id (PK)", "prescription_id (FK)", "extracted_text", "line_results (JSON)", "confidence_score"])
    t["PM"] = table(26, 82, 31, "Prescription_Medicines", ["pm_id (PK)", "prescription_id (FK)", "medicine_id (FK, nullable)", "dosage, frequency, duration", "raw_text, match_confidence", "match_status, match_options"])
    t["Med"] = table(66, 82, 34, "Medicines", ["medicine_id (PK)", "medicine_name, composition", "primary_salt, secondary_salt", "form, strength, release_type", "pack_size, price", "is_discontinued", "composition_incomplete", "manufacturer, data_source"])
    t["DDI"] = table(15, 52, 27, "Drug_Interactions", ["interaction_id (PK)", "drug_a, drug_b", "drug_a_norm, drug_b_norm", "severity, data_source"])
    t["AI"] = table(50, 52, 26, "AI_Analysis", ["analysis_id (PK)", "prescription_id (FK)", "summary, risk_level", "analysis_date"])
    t["SF"] = table(84, 52, 28, "Safety_Findings", ["finding_id (PK)", "prescription_id (FK)", "issue_type, severity", "medicines_involved (JSON)", "confidence, explanation", "recommendation, data_source"])
    t["Price"] = table(15, 30, 27, "Price_Comparison", ["price_id (PK)", "pm_id, medicine_id (FK)", "row_type, price", "price_per_unit, pack_size", "savings_percent", "price_date"])
    t["GR"] = table(50, 30, 28, "Generic_Recommendations", ["gr_id (PK)", "pm_id (FK)", "recommended_medicine_id (FK)", "price_difference", "confidence_score, reason"])
    t["Rep"] = table(84, 30, 27, "Smart_Health_Report", ["report_id (PK)", "prescription_id (FK)", "report_file", "generated_date"])
    t["Log"] = table(84, 10, 27, "System_Logs", ["log_id (PK)", "user_id (FK, nullable)", "action, details", "timestamp"])

    def right(n): c, top, w, h = t[n]; return (c + w / 2, top - h / 2)
    def left(n): c, top, w, h = t[n]; return (c - w / 2, top - h / 2)
    def bottom(n, dx=0): c, top, w, h = t[n]; return (c + dx, top - h)
    def topp(n, dx=0): c, top, w, h = t[n]; return (c + dx, top)
    a = lambda p, q, lab=None, **k: arrow(ax, p, q, text=lab, fs=7.6, **k)
    a(right("Users"), left("Prescriptions"), "1 : N", off=(0, 2))
    a(right("Prescriptions"), left("OCR"), "1 : 1", off=(0, 2))
    a(bottom("Prescriptions", -8), topp("PM", 8), "1 : N", off=(8, 0))
    a(left("Med"), right("PM"), "1 : N", off=(0, 2.5))
    a(bottom("Prescriptions", 3), topp("AI"), "1 : N", off=(5, 0))
    a(bottom("Prescriptions", 10), topp("SF", -8), "1 : N", off=(8, 0))
    a(bottom("PM", -8), topp("Price", 5), "1 : N", off=(-3, 1))
    a(bottom("PM", 4), topp("GR", -6), "1 : N", off=(4, 0))
    a(bottom("Med", 0), topp("GR", 6), "recommended", off=(7, 0), dash=True)
    a(bottom("Users", 0), (14, topp("DDI")[1] + 0.001), None)
    ax.text(15, 61.5, "", fontsize=7)
    a(topp("Rep", 0), (84, 52 - 5.2 - 3.5 * 6 - 5.2), None)
    ax.text(14, 56.8, "", fontsize=7)
    ax.text(15, 25.5 - 3.5 * 6 - 5.2 + 8, "", fontsize=7)
    ax.text(50, 1.6, "Drug_Interactions is linked to Medicines by ingredient name only (no foreign key).\n"
                    "System_Logs references Users; Smart_Health_Report references Prescriptions.", ha="center", fontsize=8.4, style="italic")
    save(fig, "fig3_2_er_diagram.png")


# ---------------------------------------------------------------- Fig 3.3 sequence
def fig_seq():
    fig, ax = new(7.6, 9.2, (-2, 104), (0, 118))
    names = ["User", "React\nfrontend", "Flask API", "OCR engine", "Decision\nservices", "MySQL"]
    xs = [8, 25, 43, 61, 79, 94]
    top = 112
    for n, x in zip(names, xs):
        box(ax, x, top, 15, 7.5, n, fc=C_BLUE, fs=8.6, bold=True)
        ax.plot([x, x], [top - 4, 2], color="#777777", lw=1, ls=(0, (5, 3)), zorder=0)
    msgs = [
        (0, 1, "1  Register / log in", False),
        (1, 2, "2  POST /api/auth/login", False),
        (2, 5, "3  Check email, verify password hash", False),
        (2, 1, "4  JWT access token", True),
        (0, 1, "5  Choose prescription file", False),
        (1, 2, "6  POST /api/prescriptions/upload", False),
        (2, 3, "7  Image / PDF page", False),
        (3, 2, "8  Words, boxes, confidences", True),
        (2, 2, "9  Group into lines; readability check", False),
        (2, 4, "10  Match each line to a medicine", False),
        (4, 5, "11  Query Medicines (full-text, brand prefix)", False),
        (4, 2, "12  Match status per line", True),
        (2, 5, "13  Store prescription, OCR result, lines", False),
        (2, 1, "14  Lines + status; unsure lines flagged", True),
        (0, 1, "15  Confirm / choose product for unsure line", False),
        (1, 2, "16  PATCH .../medicines/<pm_id> (confirm)", False),
        (2, 4, "17  Safety, price and alternatives for confirmed lines", False),
        (4, 5, "18  DDInter pairs, prices; store findings", False),
        (4, 2, "19  Analysis, prices, alternatives", True),
        (2, 1, "20  Smart Health Report (view / PDF)", True),
        (1, 0, "21  Display report", True),
    ]
    y = top - 10
    step = 4.7
    for i, (s, d, label, ret) in enumerate(msgs):
        if s == d:
            x = xs[s]
            ax.add_patch(Rectangle((x - 0.8, y - 1.6), 1.6, 3.2, fc="white", ec=EDGE, lw=1))
            ax.text(x + 2.2, y, label, ha="left", va="center", fontsize=7.8)
        else:
            arrow(ax, (xs[s], y), (xs[d], y), dash=ret)
            lx = (xs[s] + xs[d]) / 2
            ax.text(lx, y + 1.3, label, ha="center", va="bottom", fontsize=7.6, zorder=5,
                    bbox=dict(fc="white", ec="none", pad=0.6))
        y -= step
    save(fig, "fig3_3_sequence.png")


# ---------------------------------------------------------------- Fig 3.4 DFD level 0
def fig_dfd0():
    fig, ax = new(7.4, 3.6, (0, 100), (0, 48))
    box(ax, 12, 24, 20, 10, "User", fc=C_GREY, fs=11, bold=True, rounded=False)
    ax.add_patch(Ellipse((50, 24), 30, 24, fc=C_BLUE, ec=EDGE, lw=1.5, zorder=2))
    ax.text(50, 24, "0\nPharmaCompare\nSystem", ha="center", va="center", fontsize=11, fontweight="bold", zorder=3)
    box(ax, 88, 38, 22, 9, "Smart Health\nReport (PDF)", fc=C_GREY, fs=9.5, rounded=False)
    box(ax, 88, 10, 22, 9, "Cloud Vision /\nEasyOCR", fc=C_GREY, fs=9.5, rounded=False)
    # data store
    ax.plot([37, 63], [4.5, 4.5], color=EDGE, lw=1.4); ax.plot([37, 63], [0.5, 0.5], color=EDGE, lw=1.4)
    ax.plot([37, 37], [0.5, 4.5], color=EDGE, lw=1.4)
    ax.text(50, 2.5, "MySQL database and reference data", ha="center", va="center", fontsize=9)
    arrow(ax, (22, 28), (35.2, 28), "Prescription file,\nallergies, confirmations", fs=8.4, off=(0, 4.2))
    arrow(ax, (35.2, 20), (22, 20), "Analysis, prices,\nalternatives", fs=8.4, off=(0, -4.6))
    arrow(ax, (63, 30), (77, 37), "Report", fs=8.4, off=(0, 2.0))
    arrow(ax, (63, 18), (77, 11.5), "Image", fs=8.4, off=(0, -1.8))
    arrow(ax, (77, 8.5), (60, 15.5), "Text + confidence", fs=8.4, off=(7.5, -4.0))
    arrow(ax, (50, 12), (50, 4.6), both=True)
    save(fig, "fig3_4_dfd0.png")


# ---------------------------------------------------------------- Fig 3.5 DFD level 1
def fig_dfd1():
    fig, ax = new(7.6, 7.3, (0, 100), (0, 118))
    box(ax, 10, 100, 17, 10, "User", fc=C_GREY, fs=11, bold=True, rounded=False)
    procs = [("1.0\nCapture and\nextract (OCR)", 38, 106), ("2.0\nDetect and\nconfirm medicines", 38, 82), ("3.0\nAnalyze\nsafety", 38, 58),
             ("4.0\nCompare prices,\nrecommend", 38, 34), ("5.0\nGenerate\nreport", 38, 10)]
    for t, x, y in procs:
        ax.add_patch(Ellipse((x, y), 26, 15.5, fc=C_BLUE, ec=EDGE, lw=1.4, zorder=2))
        ax.text(x, y, t, ha="center", va="center", fontsize=8.8, zorder=3, linespacing=1.15)
    def store(x, y, w, label):
        ax.plot([x - w / 2, x + w / 2], [y + 3.2, y + 3.2], color=EDGE, lw=1.4)
        ax.plot([x - w / 2, x + w / 2], [y - 3.2, y - 3.2], color=EDGE, lw=1.4)
        ax.plot([x - w / 2, x - w / 2], [y - 3.2, y + 3.2], color=EDGE, lw=1.4)
        ax.text(x + 0.8, y, label, ha="center", va="center", fontsize=8.4)
    store(82, 106, 28, "D1  Prescriptions + OCR")
    store(82, 90, 28, "D2  Medicines (reference)")
    store(82, 74, 28, "D3  Matched lines")
    store(82, 58, 28, "D4  Drug_Interactions")
    store(82, 44, 28, "D5  Analysis + findings")
    store(82, 30, 28, "D6  Prices + recommendations")
    store(82, 10, 28, "D7  Smart_Health_Report")
    box(ax, 10, 20, 17, 9, "Smart Health\nReport", fc=C_GREY, fs=9, rounded=False)
    a = lambda p, q, lab=None, **k: arrow(ax, p, q, text=lab, fs=7.8, **k)
    a((18.5, 102), (25, 106.5), "Prescription\nfile", off=(-3, 5))
    a((38, 98.2), (38, 89.8), "Text lines +\nconfidence", off=(9.5, 0))
    a((51, 106), (68, 106), None, both=True)
    a((51, 82), (68, 90), "Candidates", off=(-1, 3.2), both=True)
    a((51, 80), (68, 74.5), "Lines + status", off=(-1, -3.2))
    a((18.5, 97), (25, 80), "Confirm /\nchoose", off=(-6, -4))
    a((38, 74.2), (38, 65.8), "Confirmed\nlines", off=(9, 0))
    a((51, 58), (68, 58), None, both=True)
    a((51, 56), (68, 45.5), "Findings", off=(-1, -3))
    a((38, 50.2), (38, 41.8), "Confirmed\nlines", off=(9, 0))
    a((51, 34), (68, 30.5), "Prices,\nalternatives", off=(-2, 3.5))
    a((38, 26.2), (38, 17.8), "Findings, prices,\nalternatives", off=(11, 0))
    a((51, 10), (68, 10), "PDF", off=(0, 2.5))
    a((25, 12), (18.5, 17), None)
    a((12.5, 24.5), (12.5, 95), "Analysis, prices, alternatives, report", off=(-0.0, 0), dash=True, rad=0.0) if False else None
    save(fig, "fig3_5_dfd1.png")


# ---------------------------------------------------------------- Fig 3.6 flowchart
def fig_flow():
    fig, ax = new(6.6, 10.4, (0, 100), (-6, 152))
    X = 38
    def b(y, t, fc=C_BLUE, w=56, h=7.5): box(ax, X, y, w, h, t, fc=fc, fs=9.3)
    box(ax, X, 148, 24, 6, "START", fc=C_GREEN, fs=10, bold=True)
    b(137, "User registers / logs in")
    b(126, "Upload prescription (JPG, PNG or PDF)")
    diamond(ax, X, 112, 44, 14, "Image clear?\n(mean confidence >= 0.35)")
    box(ax, 88, 112, 20, 10, "Ask user to\nre-upload", fc=C_RED, fs=9)
    arrow(ax, (X + 22, 112), (78, 112), "No", off=(0, 2)); arrow(ax, (88, 117), (88, 126), None); arrow(ax, (88, 126), (X + 28, 126), None)
    b(96, "OCR text grouped into lines; each line\nmatched to the medicine dataset", h=9)
    diamond(ax, X, 80, 48, 14, "Line settled automatically?\n(score + identity evidence)")
    box(ax, 88, 80, 20, 12, "needs_verification:\nuser picks or\nsearches product", fc=C_RED, fs=8.6)
    arrow(ax, (X + 24, 80), (78, 80), "No", off=(0, 2.2))
    b(64, "Confirmed lines only\n(matched or user_confirmed)", h=9)
    arrow(ax, (88, 74), (88, 64), None); arrow(ax, (88, 64), (X + 28, 64), "user confirms", off=(-1, 2.6))
    diamond(ax, X, 49, 50, 14, "Interaction, duplicate or\nallergy risk found?")
    box(ax, 88, 49, 20, 9, "Display safety\nalert", fc=C_RED, fs=9)
    arrow(ax, (X + 25, 49), (78, 49), "Yes", off=(0, 2.2))
    b(33, "Price comparison: same ingredients, strength,\nform, release type, pack quantity", h=9)
    b(21, "Generic / cheaper-alternative recommendation\n(up to three options, with reasons)", h=9)
    b(10, "Generate Smart Health Report (view / PDF)")
    box(ax, X, -0.5, 24, 6, "END", fc=C_GREEN, fs=10, bold=True)
    arrow(ax, (X, 145), (X, 140.8)); arrow(ax, (X, 133.2), (X, 129.8)); arrow(ax, (X, 122.2), (X, 119.0))
    arrow(ax, (X, 105), (X, 100.6), "Yes", off=(5, 0)); arrow(ax, (X, 91.5), (X, 87.0))
    arrow(ax, (X, 73), (X, 68.6), "Yes", off=(5, 0)); arrow(ax, (X, 59.4), (X, 56.0))
    arrow(ax, (88, 44.5), (88, 40), None); arrow(ax, (88, 40), (X + 25, 40), "continue", off=(0, 2)); arrow(ax, (X, 42), (X, 37.6), "No", off=(5, 0))
    arrow(ax, (X, 28.4), (X, 25.6)); arrow(ax, (X, 16.4), (X, 13.8)); arrow(ax, (X, 6.2), (X, 2.6))
    save(fig, "fig3_6_flowchart.png")


# ---------------------------------------------------------------- Fig 3.7 matching decision
def fig_match():
    fig, ax = new(7.4, 4.8, (0, 100), (0, 66))
    box(ax, 12, 52, 20, 14, "Prescription\nline text", fc=C_BLUE, fs=9.5)
    box(ax, 38, 52, 22, 14, "Candidate\nretrieval\n(full-text +\nbrand prefix)", fc=C_YEL, fs=9)
    box(ax, 64, 52, 22, 14, "Score and\ncorroborate\n(strength, form,\nrelease, salt)", fc=C_YEL, fs=9)
    arrow(ax, (22, 52), (27, 52)); arrow(ax, (49, 52), (53, 52)); arrow(ax, (75, 52), (80.5, 52))
    diamond(ax, 88, 52, 22, 20, "Settled?\n(s >= 0.90, exact\nwords or ingr.)", fs=7.4)
    box(ax, 88, 26, 22, 12, "matched", fc=C_GREEN, fs=10, bold=True)
    box(ax, 55, 26, 28, 12, "needs_verification\n(closest guess or options)", fc=C_RED, fs=9)
    box(ax, 22, 26, 24, 12, "user_confirmed\n(user presses Confirm)", fc=C_GREEN, fs=9)
    arrow(ax, (88, 42), (88, 32), "yes", off=(4, 0))
    arrow(ax, (82, 44), (62, 32), "no", off=(1, 3))
    arrow(ax, (41, 26), (34, 26), None)
    ax.text(37.5, 19.2, "user picks /\nsearches", ha="center", fontsize=7.8, style="italic")
    box(ax, 55, 6, 80, 8, "Safety, price and recommendation stages accept only matched or\nuser_confirmed lines", fc=C_PURP, fs=9)
    arrow(ax, (88, 20), (80, 10), None); arrow(ax, (22, 20), (30, 10), None)
    arrow(ax, (55, 20), (55, 10), None, dash=True) if False else None
    ax.text(62, 14.5, "needs_verification lines are held back", ha="left", fontsize=8, style="italic") if False else None
    save(fig, "fig3_7_matching.png")


def fig_er2():
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
        "System_Logs": ["log_id (PK)", "user_id (FK, null)", "action", "timestamp, details"],
        "Drug_Interactions": ["interaction_id (PK)", "drug_a, drug_b", "drug_a_norm, drug_b_norm", "severity, data_source"],
        "Smart_Health_Report": ["report_id (PK)", "prescription_id (FK)", "report_file", "generated_date"],
    }
    grid = [["Users", "Prescriptions", "OCR_Results"],
            ["AI_Analysis", "Prescription_Medicines", "Safety_Findings"],
            ["Price_Comparison", "Medicines", "Generic_Recommendations"],
            ["System_Logs", "Drug_Interactions", "Smart_Health_Report"]]
    lh, hh, gap = 2.75, 4.4, 10
    pos = {}
    top = 0
    for row in grid:
        rh = max(hh + lh * len(tables[n]) for n in row)
        for c, n in zip(cols, row):
            pos[n] = (c, top, hh + lh * len(tables[n]))
        top -= rh + gap
    total = -top
    fig, ax = new(7.6, 7.6 * (total - top * 0 + 4) / 100 * 1.0 - 0.0 if False else 7.6 * (3 - (top + gap - 1)) / 100, (0, 100), (top + gap - 1, 3))
    for n, (cx, tp, h) in pos.items():
        ax.add_patch(Rectangle((cx - W / 2, tp - h), W, h, fc=C_PURP, ec=EDGE, lw=1.3, zorder=2))
        ax.add_patch(Rectangle((cx - W / 2, tp - hh), W, hh, fc="#cfd9e8", ec=EDGE, lw=1.3, zorder=3))
        ax.text(cx, tp - hh / 2, n, ha="center", va="center", fontsize=8.9, fontweight="bold", zorder=4)
        for i, f in enumerate(tables[n]):
            ax.text(cx - W / 2 + 1.0, tp - hh - lh * (i + 0.62), f, ha="left", va="center", fontsize=7.7, zorder=4)
    L = lambda n, y=None: (pos[n][0] - W / 2, pos[n][1] - pos[n][2] / 2 if y is None else y)
    R = lambda n, y=None: (pos[n][0] + W / 2, pos[n][1] - pos[n][2] / 2 if y is None else y)
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
    yM = pos["Medicines"][1] - 10
    lab((L("Medicines")[0], yM), (R("Price_Comparison")[0], yM), None)
    lab((R("Medicines")[0], yM), (L("Generic_Recommendations")[0], yM), None)
    lab(B("Medicines"), T("Drug_Interactions"), "by ingredient name", dash=True, off=(10.5, 0))
    ax.text(50, top + gap - 0.5, "Dashed link: no foreign key (matched by ingredient name). * One OCR row per upload by application logic; not enforced by a unique key.\n"
            "Not drawn: System_Logs.user_id (FK to Users) and Smart_Health_Report.prescription_id (FK to Prescriptions).", ha="center", va="top", fontsize=7.8, style="italic")
    save(fig, "fig3_2_er_diagram.png")


def fig_dfd0b():
    fig, ax = new(7.4, 3.9, (0, 100), (-2, 52))
    box(ax, 11, 28, 18, 10, "User", fc=C_GREY, fs=11, bold=True, rounded=False)
    ax.add_patch(Ellipse((50, 28), 30, 24, fc=C_BLUE, ec=EDGE, lw=1.5, zorder=2))
    ax.text(50, 28, "0\nPharmaCompare\nSystem", ha="center", va="center", fontsize=11, fontweight="bold", zorder=3)
    box(ax, 89, 44, 20, 9, "Smart Health\nReport (PDF)", fc=C_GREY, fs=9.5, rounded=False)
    box(ax, 89, 13, 20, 9, "Cloud Vision /\nEasyOCR", fc=C_GREY, fs=9.5, rounded=False)
    ax.plot([30, 70], [3.5, 3.5], color=EDGE, lw=1.4); ax.plot([30, 70], [-0.5, -0.5], color=EDGE, lw=1.4)
    ax.plot([30, 30], [-0.5, 3.5], color=EDGE, lw=1.4); ax.plot([70, 70], [-0.5, 3.5], color=EDGE, lw=1.4)
    ax.text(50, 1.5, "MySQL database and reference data", ha="center", va="center", fontsize=9)
    arrow(ax, (20, 32), (35.3, 32), "Prescription file, allergies,\nconfirmations", fs=8.4, off=(-1, 5.5))
    arrow(ax, (35.3, 24), (20, 24), "Analysis, prices,\nalternatives", fs=8.4, off=(-1, -5.5))
    arrow(ax, (63, 35), (79, 42), "Report", fs=8.4, off=(-3, 2.5))
    arrow(ax, (63, 22), (79, 15.5), "Image", fs=8.4, off=(-2, 3.2))
    arrow(ax, (79, 11), (60.5, 20), "Text + confidence", fs=8.4, off=(2, -5.5))
    arrow(ax, (50, 16), (50, 3.7), both=True)
    save(fig, "fig3_4_dfd0.png")


if __name__ == "__main__":
    fig_cycle(); fig_arch(); fig_er2(); fig_seq(); fig_dfd0b(); fig_dfd1(); fig_flow(); fig_match()

