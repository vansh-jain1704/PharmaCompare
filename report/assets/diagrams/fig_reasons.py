"""Bar chart of the experiment-A rejection reasons, from paper/results/experiment_results_2026-10-16.json."""
import json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
for f in ("times.ttf", "timesbd.ttf"):
    p = os.path.join(r"C:\Windows\Fonts", f)
    if os.path.exists(p):
        font_manager.fontManager.addfont(p)
plt.rcParams["font.family"] = "Times New Roman"
d = json.load(open(r"D:\PharmaCompare\paper\results\experiment_results_2026-10-16.json"))["E_A"]
r = d["rejection_reasons_first_failing_rule"]
total = d["naive_cheapest_rejected_by_strict_rules"]
assert sum(r.values()) == total == 460
items = sorted(r.items(), key=lambda kv: kv[1])
fig, ax = plt.subplots(figsize=(6.4, 3.2))
ax.barh([k.capitalize() for k, _ in items], [v for _, v in items], color="#4a7fc1", edgecolor="#222222", linewidth=0.8)
for y, (_, v) in enumerate(items):
    ax.text(v + 3, y, f"{v} ({100 * v / total:.1f}%)", va="center", fontsize=9)
ax.set_xlim(0, 235)
ax.set_xlabel(f"Products (n = {total} rejected suggestions)", fontsize=10)
ax.spines[["top", "right"]].set_visible(False)
ax.tick_params(labelsize=9.5)
fig.savefig(sys.argv[1], dpi=200, bbox_inches="tight", facecolor="white")
print("saved")
