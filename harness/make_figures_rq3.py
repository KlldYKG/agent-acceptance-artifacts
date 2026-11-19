# -*- coding: utf-8 -*-
"""Generate the English RQ3 ablation figure from verified aggregate values."""
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

GREEN = "#0F6E56"
BLUE = "#185FA5"
RUST = "#993C1D"
GRAY = "#7A7A7A"
AMBER = "#C07A00"

fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.0), dpi=150,
                         gridspec_kw={"width_ratios": [1.15, 1.35, 1.05]})

# Panel (a): A-full vs A1.
ax = axes[0]
metrics = ["TCR\n(task completion)", "Tasks requiring repair", "Total rounds", "Agent cost\n($)"]
a1 = [100, 21, 84, 0.885]
af = [100, 20, 83, 0.795]
xmax = [110, 26, 100, 1.05]
for i, (x1, x2, xm) in enumerate(zip(a1, af, xmax)):
    y = i
    plot1 = x1 / xm * 100
    plot2 = x2 / xm * 100
    ax.barh(y + 0.18, plot1, height=0.32, color=BLUE,
            label="A1 (gold-test acceptance)" if i == 0 else None)
    ax.barh(y - 0.18, plot2, height=0.32, color=GREEN,
            label="A-full (+ mutation)" if i == 0 else None)
    ax.text(plot1 + 2, y + 0.18, f"{x1:g}", va="center", fontsize=9.5, color=BLUE)
    ax.text(plot2 + 2, y - 0.18, f"{x2:g}", va="center", fontsize=9.5, color=GREEN)
ax.set_yticks(range(len(metrics)))
ax.set_yticklabels(metrics, fontsize=9.5)
ax.invert_yaxis()
ax.set_xlim(0, 118)
ax.set_xlabel("Within-metric scaled value (0–100)", fontsize=9)
ax.set_title("(a) Head-to-head: A-full vs A1\n(6 runs × 63 tasks each; opencode × flash)", fontsize=11)
ax.grid(axis="x", alpha=0.3, lw=0.5)
ax.legend(fontsize=8.2, loc="upper center", bbox_to_anchor=(0.5, -0.28), framealpha=0.9)
ax.text(0.5, -0.50, "TCR gain = 0 (ceiling); other differences are descriptive",
        fontsize=9, color=GRAY, ha="center", transform=ax.transAxes)

# Panel (b): mutation-reachability funnel.
ax = axes[1]
stages = [
    ("63 tasks\n(full A-full batch)", 63, BLUE),
    ("6 tasks with test files (9.5%)", 6, BLUE),
    ("3 × TIMEOUT\n(C1: 800+ mutants / 300 s budget)", 3, AMBER),
    ("3 × baseline-blocked\n(D1: broken agent tests stop mutmut)", 3, RUST),
    ("In-batch mutation scores: 0", 0, GRAY),
]
widths = [stage[1] for stage in stages]
maxw = max(widths)
for i, (label, width, color) in enumerate(stages):
    left = (maxw - width) / 2 if width > 0 else maxw * 0.42
    ax.barh(i, max(width, 0.6), left=left, height=0.62, color=color, alpha=0.88)
    ax.text(maxw / 2, i, f"{width}", ha="center", va="center",
            fontsize=11, fontweight="bold", color="white" if width > 0 else GRAY)
    ax.text(maxw * 1.03, i, label, ha="left", va="center", fontsize=8.3)
    if i < len(stages) - 1:
        ax.annotate("", xy=(maxw / 2, i + 0.78), xytext=(maxw / 2, i + 0.28),
                    arrowprops=dict(arrowstyle="-|>", color=GRAY, lw=1.2))
ax.set_xlim(0, maxw * 2.25)
ax.set_ylim(-0.55, len(stages) - 0.3)
ax.invert_yaxis()
ax.axis("off")
ax.set_title("(b) Mutation-reachability funnel: three constraints\n(In-batch scores = 0/63)", fontsize=11)

# Panel (c): budget sensitivity.
ax = axes[2]
budgets = ["150 s", "300 s\n(CI budget)", "900 s"]
colors = [AMBER, AMBER, GREEN]
labels = ["TIMEOUT", "TIMEOUT", "OK\nscore 1.0"]
bars = ax.bar(budgets, [1, 1, 1], width=0.58, color=colors, alpha=0.88)
for bar, label in zip(bars, labels):
    ax.text(bar.get_x() + bar.get_width() / 2, 0.5, label, ha="center", va="center",
            fontsize=10.5, fontweight="bold", color="white")
ax.annotate("killed = 874, survived = 0\n(885 s elapsed; ≈1 mutant/s)",
            xy=(2, 1.0), xytext=(0.28, 1.24), fontsize=9,
            arrowprops=dict(arrowstyle="-|>", color=GRAY, lw=1.1), color=GREEN)
ax.text(0.5, 1.10, "Explicit degradation: no fabricated score", fontsize=9.2,
        color=AMBER, ha="center", fontweight="bold")
ax.set_ylim(0, 1.52)
ax.set_yticks([])
ax.set_xlabel("Mutation-phase budget\n(C4 offline smoke test, sqlparse)", fontsize=10)
ax.set_title("(c) Budget sensitivity\n(300 s: timeout → 900 s: complete, zero survivors)", fontsize=11)
for spine in ["top", "right", "left"]:
    ax.spines[spine].set_visible(False)

out = pathlib.Path(__file__).parent / "figures"
out.mkdir(exist_ok=True)
fig.tight_layout()
fig.savefig(out / "rq3_ablation.png", bbox_inches="tight")
plt.close(fig)
print("saved", out / "rq3_ablation.png")
