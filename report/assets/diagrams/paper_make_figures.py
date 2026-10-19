import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon, FancyArrowPatch

HERE = os.path.dirname(os.path.abspath(__file__))
RES = json.load(open(os.path.join(HERE, "..", "results", "experiment_results_2026-10-16.json"), encoding="utf-8"))
plt.rcParams["font.family"] = "Times New Roman"
plt.rcParams["font.size"] = 7
W = 3.45
DPI = 300
FILL = {"ui": "#e8eef7", "api": "#e9f3e6", "proc": "#fdf2dc", "data": "#f1e6f3", "ext": "#eeeeee", "stop": "#fbe3e0"}


def box(ax, x, y, w, h, text, kind="proc", fs=6.4, bold=False):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.015", fc=FILL[kind], ec="#333333", lw=0.7)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, fontweight="bold" if bold else "normal", linespacing=1.15)


def arrow(ax, x1, y1, x2, y2, text=None, both=False, dashed=False, tx=0.0, ty=0.0):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="<|-|>" if both else "-|>", mutation_scale=7, lw=0.7, color="#222222",
                        linestyle="--" if dashed else "-", shrinkA=0, shrinkB=0)
    ax.add_patch(a)
    if text:
        ax.text((x1 + x2) / 2 + tx, (y1 + y2) / 2 + ty, text, fontsize=5.8, ha="center", va="center", style="italic",
                bbox=dict(fc="white", ec="none", pad=0.4))


def diamond(ax, cx, cy, w, h, text, fs=6.2):
    ax.add_patch(Polygon([(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)], closed=True, fc="#fff8e1", ec="#333333", lw=0.7))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, linespacing=1.1)


# ---------------------------------------------------------------- Fig 1 architecture
def fig_architecture():
    fig, ax = plt.subplots(figsize=(W, 4.3))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    box(ax, 0.20, 0.915, 0.60, 0.075, "User (browser)", "ext", bold=True)
    box(ax, 0.06, 0.795, 0.88, 0.085, "Presentation layer\nReact 19 + Vite SPA: upload, verify, report, search, profile", "ui")
    box(ax, 0.06, 0.675, 0.88, 0.085, "Flask REST API (Blueprints)\nJWT authentication, password hashing, request validation", "api")
    # processing row 1
    box(ax, 0.02, 0.50, 0.30, 0.13, "OCR service\nline grouping,\nreadability gate", "proc")
    box(ax, 0.35, 0.50, 0.30, 0.13, "Medicine\nmatching +\nmatch status", "proc")
    box(ax, 0.68, 0.50, 0.30, 0.13, "Safety engine\ninteractions, duplicates,\ndose check, allergy", "proc")
    box(ax, 0.02, 0.33, 0.30, 0.13, "Price\ncomparison\n+ price quality", "proc")
    box(ax, 0.35, 0.33, 0.30, 0.13, "Alternatives\n(comparable,\ncheaper)", "proc")
    box(ax, 0.68, 0.33, 0.30, 0.13, "PDF report\n(reportlab)", "proc")
    # data
    box(ax, 0.06, 0.15, 0.50, 0.12, "MySQL 12 tables\nusers, prescriptions, OCR, medicines,\ninteractions, findings, prices, reports", "data")
    box(ax, 0.60, 0.15, 0.36, 0.12, "Reference data\nmedicine dataset (static)\nDDInter 2.0 pairs", "data")
    # external
    box(ax, 0.02, 0.01, 0.30, 0.095, "Google Cloud\nVision (primary OCR)", "ext", fs=6)
    box(ax, 0.35, 0.01, 0.30, 0.095, "EasyOCR\n(local fallback)", "ext", fs=6)
    box(ax, 0.68, 0.01, 0.30, 0.095, "Gemini (optional,\nexplanations only)", "ext", fs=6)
    arrow(ax, 0.5, 0.915, 0.5, 0.88, both=True)
    arrow(ax, 0.5, 0.795, 0.5, 0.76, both=True)
    arrow(ax, 0.5, 0.675, 0.5, 0.645, both=False)
    ax.plot([0.17, 0.83], [0.645, 0.645], color="#222222", lw=0.7)
    for x in (0.17, 0.5, 0.83):
        arrow(ax, x, 0.645, x, 0.63)
    arrow(ax, 0.32, 0.565, 0.35, 0.565)
    arrow(ax, 0.65, 0.565, 0.68, 0.565)
    arrow(ax, 0.17, 0.50, 0.17, 0.46, dashed=True)
    arrow(ax, 0.32, 0.395, 0.35, 0.395)
    arrow(ax, 0.65, 0.395, 0.68, 0.395)
    arrow(ax, 0.31, 0.33, 0.31, 0.27, both=True, dashed=True)
    arrow(ax, 0.78, 0.33, 0.78, 0.27, both=True, dashed=True)
    arrow(ax, 0.17, 0.15, 0.17, 0.105, dashed=True)
    arrow(ax, 0.50, 0.15, 0.50, 0.105, dashed=True)
    arrow(ax, 0.83, 0.15, 0.83, 0.105, dashed=True)
    fig.savefig(os.path.join(HERE, "fig1_architecture.png"), dpi=DPI, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


# ---------------------------------------------------------------- Fig 2 workflow
def fig_workflow():
    fig, ax = plt.subplots(figsize=(W, 5.9))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    cx = 0.40
    def pill(y, text):
        box(ax, cx - 0.22, y, 0.44, 0.05, text, "ui", fs=6.2)
    pill(0.945, "Login / register (JWT)")
    pill(0.875, "Upload image or PDF")
    pill(0.805, "OCR: Cloud Vision, else EasyOCR")
    pill(0.735, "Group fragments into lines;\nmean confidence")
    diamond(ax, cx, 0.645, 0.46, 0.085, "Mean confidence\n>= 0.35 ?")
    box(ax, 0.73, 0.62, 0.26, 0.05, "Ask for a clearer\nimage (stop)", "stop", fs=5.8)
    pill(0.545, "Match each line to the\nmedicine dataset")
    diamond(ax, cx, 0.455, 0.50, 0.095, "Settled automatically\n(score, identity evidence)?")
    box(ax, 0.73, 0.40, 0.26, 0.10, "needs_verification:\nclosest guess shown;\nuser picks or searches", "stop", fs=5.6)
    pill(0.345, "Confirmed lines only")
    pill(0.275, "Safety checks: DDInter pairs,\nduplicates, dose, allergy")
    pill(0.205, "Price comparison: same ingredients,\nstrength, form, release, pack")
    pill(0.135, "Cheaper comparable options\n(max. 3 per medicine)")
    pill(0.065, "Smart Health Report (PDF)")
    for y1, y2 in [(0.945, 0.925), (0.875, 0.855), (0.805, 0.785), (0.735, 0.688), (0.602, 0.595), (0.5, 0.395), (0.345, 0.325), (0.275, 0.255), (0.205, 0.185), (0.135, 0.115)]:
        pass
    arrow(ax, cx, 0.945, cx, 0.925); arrow(ax, cx, 0.875, cx, 0.855); arrow(ax, cx, 0.805, cx, 0.785)
    arrow(ax, cx, 0.735, cx, 0.688)
    arrow(ax, cx + 0.23, 0.645, 0.73, 0.645, "no", ty=0.02)
    arrow(ax, cx, 0.602, cx, 0.595, "yes", tx=0.05)
    arrow(ax, cx, 0.545, cx, 0.503)
    arrow(ax, cx + 0.25, 0.455, 0.73, 0.455, "no", ty=0.02)
    arrow(ax, cx, 0.408, cx, 0.395, "yes", tx=0.05)
    arrow(ax, 0.86, 0.40, 0.86, 0.37)
    ax.plot([0.86, 0.62], [0.37, 0.37], color="#222222", lw=0.7)
    arrow(ax, 0.62, 0.37, 0.62, 0.371)
    ax.text(0.86, 0.352, "after user\nconfirmation", fontsize=5.6, ha="center", style="italic")
    arrow(ax, 0.86, 0.355, 0.63, 0.355 - 0.0)
    arrow(ax, cx, 0.345, cx, 0.325); arrow(ax, cx, 0.275, cx, 0.255); arrow(ax, cx, 0.205, cx, 0.185); arrow(ax, cx, 0.135, cx, 0.115)
    fig.savefig(os.path.join(HERE, "fig2_workflow.png"), dpi=DPI, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


# ---------------------------------------------------------------- Fig 3 ER (core)
def fig_er():
    fig, ax = plt.subplots(figsize=(W, 3.35))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    def table(x, y, w, h, title, fields, kind="data"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="square,pad=0", fc=FILL[kind], ec="#333333", lw=0.7))
        ax.add_patch(FancyBboxPatch((x, y + h - 0.075), w, 0.075, boxstyle="square,pad=0", fc="#cfd8e6", ec="#333333", lw=0.7))
        ax.text(x + w / 2, y + h - 0.0375, title, ha="center", va="center", fontsize=6.0, fontweight="bold")
        ax.text(x + 0.012, y + h - 0.095, "\n".join(fields), ha="left", va="top", fontsize=5.1, linespacing=1.18)
    table(0.01, 0.74, 0.25, 0.25, "Users", ["user_id PK", "name, email, phone", "password (hash)", "allergies"])
    table(0.36, 0.74, 0.28, 0.25, "Prescriptions", ["prescription_id PK", "user_id FK", "image_path, status", "upload_date, name"])
    table(0.74, 0.74, 0.25, 0.25, "OCR_Results", ["ocr_id PK", "prescription_id FK", "extracted_text", "confidence_score"])
    table(0.01, 0.40, 0.31, 0.27, "Prescription_Medicines", ["pm_id PK", "prescription_id FK", "medicine_id FK", "raw_text, match_status", "match_confidence", "dosage, frequency, duration"])
    table(0.40, 0.40, 0.27, 0.27, "Medicines (253,973)", ["medicine_id PK", "name, composition", "primary/secondary salt", "strength, form, release", "pack_size, price", "is_discontinued"])
    table(0.74, 0.40, 0.25, 0.27, "Drug_Interactions", ["interaction_id PK", "drug_a, drug_b", "severity (DDInter)", "data_source"])
    table(0.01, 0.04, 0.30, 0.27, "Price_Comparison", ["price_id PK", "pm_id FK, medicine_id FK", "row_type, price", "price_per_unit", "savings_percent", "price_date, data_source"])
    table(0.36, 0.04, 0.30, 0.27, "Generic_Recommendations", ["gr_id PK", "pm_id FK", "recommended_medicine_id FK", "price_difference", "confidence_score, reason"])
    table(0.71, 0.04, 0.28, 0.27, "Safety_Findings /\nAI_Analysis / Report", ["finding_id PK", "prescription_id FK", "issue_type, severity", "explanation", "report_file"])
    ax.annotate("", xy=(0.36, 0.865), xytext=(0.26, 0.865), arrowprops=dict(arrowstyle="-|>", lw=0.7))
    ax.annotate("", xy=(0.74, 0.865), xytext=(0.64, 0.865), arrowprops=dict(arrowstyle="-|>", lw=0.7))
    ax.annotate("", xy=(0.17, 0.67), xytext=(0.45, 0.74), arrowprops=dict(arrowstyle="-|>", lw=0.7))
    ax.annotate("", xy=(0.40, 0.535), xytext=(0.32, 0.535), arrowprops=dict(arrowstyle="-|>", lw=0.7))
    ax.annotate("", xy=(0.16, 0.31), xytext=(0.16, 0.40), arrowprops=dict(arrowstyle="<|-", lw=0.7))
    ax.annotate("", xy=(0.50, 0.31), xytext=(0.20, 0.40), arrowprops=dict(arrowstyle="<|-", lw=0.7))
    ax.annotate("", xy=(0.84, 0.31), xytext=(0.52, 0.74), arrowprops=dict(arrowstyle="<|-", lw=0.6, ls="--"))
    ax.text(0.70, 0.535, "name\nlookup", fontsize=5, ha="center", style="italic")
    ax.annotate("", xy=(0.74, 0.55), xytext=(0.67, 0.55), arrowprops=dict(arrowstyle="-", lw=0.6, ls="--"))
    fig.savefig(os.path.join(HERE, "fig3_er.png"), dpi=DPI, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


# ---------------------------------------------------------------- Fig 4 perturbation outcomes
def fig_outcomes():
    t = RES["E_S"]["outcomes_by_edits"]
    ks = ["0", "1", "2", "3"]
    n = RES["E_S"]["sample_size"]
    def pct(keys, k):
        return 100 * sum(t[k][key] for key in keys) / n
    series = [
        ("Auto-accepted, correct or equivalent product", ["auto_correct_product", "auto_equivalent_product"], "#4a7ebb"),
        ("Auto-accepted, wrong product", ["auto_wrong"], "#c0392b"),
        ("User chooses (options shown)", ["choice_offered_truth_listed", "choice_offered_truth_missing"], "#8fb8de"),
        ("Needs verification, true product suggested", ["needs_verification_truth_suggested"], "#e6c35c"),
        ("Needs verification, no correct guess", ["needs_verification_other_or_no_guess"], "#b0b0b0"),
        ("Not identified / skipped", ["not_identified"], "#555555"),
    ]
    fig, ax = plt.subplots(figsize=(W, 2.15))
    bottom = [0] * 4
    for label, keys, color in series:
        vals = [pct(keys, k) for k in ks]
        ax.bar(range(4), vals, bottom=bottom, color=color, edgecolor="white", lw=0.4, label=label, width=0.66)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_xticks(range(4)); ax.set_xticklabels(["0 (clean)", "1", "2", "3"])
    ax.set_xlabel("Simulated character edits per line", fontsize=7)
    ax.set_ylabel(f"Share of lines (%), n = {n}", fontsize=7)
    ax.set_ylim(0, 100)
    ax.legend(fontsize=5.0, loc="upper center", bbox_to_anchor=(0.5, -0.27), ncol=1, frameon=False)
    ax.tick_params(labelsize=6.5)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.savefig(os.path.join(HERE, "fig4_outcomes.png"), dpi=DPI, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


# ---------------------------------------------------------------- Fig 5 rejection reasons
def fig_reasons():
    d = RES["E_A"]["rejection_reasons_first_failing_rule"]
    items = sorted(d.items(), key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(W, 2.05))
    ax.barh([k for k, _ in items], [v for _, v in items], color="#4a7ebb", height=0.62)
    for i, (_, v) in enumerate(items):
        ax.text(v + 3, i, str(v), va="center", fontsize=6)
    ax.set_xlabel("Products (n = %d with a cheaper same-ingredient item)" % RES["E_A"]["naive_cheaper_exists"], fontsize=6.2)
    ax.tick_params(labelsize=6.3)
    ax.set_xlim(0, max(d.values()) * 1.15)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.savefig(os.path.join(HERE, "fig5_reasons.png"), dpi=DPI, bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)


if __name__ == "__main__":
    fig_architecture(); fig_workflow(); fig_er(); fig_outcomes(); fig_reasons()
    print("ok")
