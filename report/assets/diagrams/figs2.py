"""Chapter 3 diagrams, redrawn compactly and checked against the code (architecture, sequence, flow chart)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_figs as M
from make_figs import *

OUT = sys.argv[1]
M.OUT = OUT


# ---------------------------------------------------------------- Fig 3.1 architecture (landscape, editable script)
def fig_arch2():
    fig, ax = new(7.6, 4.9, (0, 100), (0, 64))
    box(ax, 9, 57, 15, 7, "User\n(web browser)", fc=C_GREY, fs=8.4, bold=True)
    box(ax, 38, 57, 36, 8, "Presentation layer: React single-page app\n(register, upload, verify, report, search)", fc=C_BLUE, fs=7.6)
    box(ax, 80, 57, 36, 8, "Application layer: Flask REST API\n(JWT authentication, validation, file checks)", fc=C_GREEN, fs=7.6)
    arrow(ax, (16.5, 57), (20, 57), both=True)
    arrow(ax, (56, 57), (62, 57), both=True)
    ax.text(59, 61.6, "JSON", ha="center", fontsize=7, style="italic")
    xs = [9, 25.5, 42, 58.5, 75, 91.5]
    ax.plot([80, 80], [53, 48], color=EDGE, lw=1.3)
    ax.plot([xs[0], xs[-1]], [48, 48], color=EDGE, lw=1.3)
    ax.text(50, 49.6, "Back-end services called by the API", ha="center", fontsize=7.2, style="italic")
    svc = ["OCR service\n(lines,\nreadability)", "Medicine\nmatching\n(match status)", "Clinical decision\nengine (safety\nchecks)",
           "Price comparison\nand alternatives", "Smart Health\nReport (PDF)", "Medicine\nexplanation"]
    for x, t in zip(xs, svc):
        box(ax, x, 38, 15.6, 11.5, t, fc=C_YEL, fs=7.2)
        arrow(ax, (x, 48), (x, 43.8))
    box(ax, 52, 13, 52, 12, "MySQL database (12 tables)\nUsers, Prescriptions, OCR_Results, Prescription_Medicines,\nfindings, prices, reports, plus the reference tables\nMedicines (253,973 products) and Drug_Interactions (160,235 pairs)", fc=C_PURP, fs=7.0)
    for x in xs[1:5]:
        arrow(ax, (x, 32.2), (x, 19.1), both=True, dash=True)
    arrow(ax, (14.5, 32.2), (26.5, 18.5), both=True, dash=True)
    arrow(ax, (88, 32.2), (78.5, 17.5), both=True, dash=True)
    box(ax, 9, 21, 15.6, 6, "Google Cloud Vision\n(primary OCR)", fc=C_GREY, fs=6.8)
    box(ax, 9, 11, 15.6, 6, "EasyOCR (local\nfallback OCR)", fc=C_GREY, fs=6.8)
    box(ax, 91.5, 12, 15.6, 6.4, "Gemini API\n(optional)", fc=C_GREY, fs=6.8)
    arrow(ax, (9, 32.2), (9, 24.2), dash=True)
    arrow(ax, (9, 18), (9, 14.2), dash=True)
    ax.text(12.5, 16.2, "if no key /\nfailure", fontsize=6.2, style="italic", va="center")
    arrow(ax, (91.5, 32.2), (91.5, 15.4), dash=True)
    save(fig, "fig3_1_architecture.png")


# ---------------------------------------------------------------- Fig 3.3 sequence (matches routes/prescriptions.py)
def fig_seq2():
    fig, ax = new(7.8, 7.4, (0, 104), (0, 100))
    names = ["User", "React\nfrontend", "Flask API", "OCR engine", "Back-end\nservices", "MySQL"]
    xs = [9, 26, 44, 62, 80, 95]
    top = 96
    for n, x in zip(names, xs):
        box(ax, x, top, 15, 6.0, n, fc=C_BLUE, fs=8.2, bold=True)
        ax.plot([x, x], [top - 3.4, 1.5], color="#777777", lw=1, ls=(0, (5, 3)), zorder=0)
    msgs = [
        (0, 1, "1  Log in", False), (1, 2, "2  POST /api/auth/login", False),
        (2, 5, "3  Read user, check password hash", False), (2, 1, "4  JWT access token", True),
        (0, 1, "5  Choose prescription file", False), (1, 2, "6  POST /api/prescriptions/upload", False),
        (2, 5, "7  Save file, INSERT Prescriptions", False), (2, 3, "8  Image (or page 1 of PDF)", False),
        (3, 2, "9  Words, boxes, confidences", True), (2, 2, "10  Group lines, readable?", False),
        (2, 5, "11  INSERT OCR_Results", False), (2, 4, "12  Match lines; safety; prices", False),
        (4, 5, "13  Read Medicines, Drug_Interactions", False), (4, 5, "14  INSERT lines, findings, prices", False),
        (2, 1, "15  Result (lines, status, analysis)", True), (0, 1, "16  Confirm a product for a line", False),
        (1, 2, "17  PATCH .../medicines/{pm_id}", False), (2, 4, "18  Re-run safety, prices, alternatives", False),
        (2, 1, "19  Updated analysis", True), (0, 1, "20  Download report", False),
        (1, 2, "21  GET .../report (PDF built, row saved)", False), (2, 0, "22  Smart Health Report (PDF)", True),
    ]
    step = 3.85
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


# ---------------------------------------------------------------- Fig 3.6 flow chart (OCR first, then readability check)
def fig_flow2():
    fig, ax = new(6.4, 8.0, (0, 100), (-6, 152))
    X = 38
    def b(y, t, fc=C_BLUE, w=56, h=7.5): box(ax, X, y, w, h, t, fc=fc, fs=9.2)
    box(ax, X, 148, 24, 6, "START", fc=C_GREEN, fs=10, bold=True)
    b(137, "User registers / logs in")
    b(126, "Upload prescription (JPG, PNG or PDF)")
    b(115, "OCR: Google Cloud Vision, or EasyOCR\nas fallback; text grouped into lines", h=9)
    diamond(ax, X, 99, 46, 14, "Page readable?\n(mean confidence >= 0.35)")
    box(ax, 88, 99, 20, 10, "Ask user to\nre-upload", fc=C_RED, fs=9)
    arrow(ax, (X + 23, 99), (78, 99), "No", off=(0, 2)); arrow(ax, (88, 104), (88, 126), None); arrow(ax, (88, 126), (X + 28, 126), None)
    b(83, "Each line matched to the medicine dataset", h=7.5)
    diamond(ax, X, 67, 48, 14, "Line settled automatically?\n(score + identity evidence)")
    box(ax, 88, 67, 20, 12, "needs_verification:\nuser picks or\nsearches product", fc=C_RED, fs=8.6)
    arrow(ax, (X + 24, 67), (78, 67), "No", off=(0, 2.2))
    b(51, "Confirmed lines only\n(matched or user_confirmed)", h=9)
    arrow(ax, (88, 61), (88, 51), None); arrow(ax, (88, 51), (X + 28, 51), "user confirms", off=(-1, 2.6))
    diamond(ax, X, 36, 50, 14, "Interaction, duplicate or\nallergy risk found?")
    box(ax, 88, 36, 20, 9, "Display safety\nalert", fc=C_RED, fs=9)
    arrow(ax, (X + 25, 36), (78, 36), "Yes", off=(0, 2.2))
    b(20, "Price comparison and cheaper-alternative\nrecommendation (same composition)", h=9)
    b(8, "Generate Smart Health Report (view / PDF)")
    box(ax, X, -2, 24, 6, "END", fc=C_GREEN, fs=10, bold=True)
    arrow(ax, (X, 145), (X, 140.8)); arrow(ax, (X, 133.2), (X, 129.8)); arrow(ax, (X, 122.2), (X, 119.6)); arrow(ax, (X, 110.4), (X, 106.0))
    arrow(ax, (X, 92), (X, 86.8), "Yes", off=(5, 0)); arrow(ax, (X, 79.2), (X, 74.0))
    arrow(ax, (X, 60), (X, 55.6), "Yes", off=(5, 0)); arrow(ax, (X, 46.4), (X, 43.0))
    arrow(ax, (88, 31.5), (88, 27)); arrow(ax, (88, 27), (X + 28, 27), "continue", off=(0, 2))
    arrow(ax, (X, 29), (X, 24.6), "No", off=(5, 0))
    arrow(ax, (X, 15.4), (X, 12.0)); arrow(ax, (X, 4.2), (X, 1.0))
    save(fig, "fig3_6_flowchart.png")


if __name__ == "__main__":
    fig_seq2(); fig_flow2()
