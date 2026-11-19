# -*- coding: utf-8 -*-
"""Generate English figures for RQ1 decay and RQ2 intervention results."""
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# Accepted runs by task position; each position has three repetitions.
POS = {
    "A (httpx)":       {1:3,2:3,3:3,4:3,5:3,6:3,7:3,8:0},
    "B (marshmallow)": {1:3,2:3,3:3,4:3,5:3,6:3,7:3,8:3,9:1,10:1,11:0},
    "C (sqlparse)":    {1:1,2:2,3:0,4:3,5:3,6:1,7:1,8:3,9:2,10:0},
    "D (click)":       {1:3,2:2,3:2,4:1,5:3,6:3,7:0,8:3,9:3,10:0,11:0},
    "E (black)":       {1:3,2:3,3:3,4:0,5:3,6:3,7:3,8:3,9:3,10:3},
}
COLORS = ["#185FA5", "#0F6E56", "#993C1D", "#534AB7", "#3B6D11"]
out = pathlib.Path(__file__).parent / "figures"
out.mkdir(exist_ok=True)

# Figure 1: position-dependent decay and agent comparison.
fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.6), dpi=150,
                         gridspec_kw={"width_ratios": [2.1, 1]})
ax = axes[0]
for (label, pos), color in zip(POS.items(), COLORS):
    xs = sorted(pos)
    ys = [pos[i] / 3 * 100 for i in xs]
    ax.plot(xs, ys, marker="o", ms=4, lw=1.8, color=color, label=label)
ax.set_xlabel("Task position within chain (1 = first task)", fontsize=11)
ax.set_ylabel("Completion rate (%)", fontsize=11)
ax.set_title("Task position vs completion — opencode × DeepSeek-flash × A0\n"
             "(3 repetitions per point)", fontsize=12)
ax.set_ylim(-6, 108)
ax.set_xticks(range(1, 12))
ax.grid(alpha=0.3, lw=0.5)
ax.legend(fontsize=9, loc="lower left", framealpha=0.9)
ax.annotate("Late-chain collapse", xy=(9.7, 12), fontsize=10, color="#A32D2D")
ax.axvspan(8.5, 11.5, color="#A32D2D", alpha=0.06)

ax2 = axes[1]
names = ["opencode\n(iterative agent)", "aider\n(single-shot blind edits)"]
vals = [73.3, 22.7]
bars = ax2.bar(names, vals, width=0.55, color=["#0F6E56", "#993C1D"])
for bar, value in zip(bars, vals):
    ax2.text(bar.get_x() + bar.get_width()/2, value + 2, f"{value:.1f}%",
             ha="center", fontsize=12, fontweight="bold")
ax2.set_ylabel("Overall task completion rate, TCR (%)", fontsize=11)
ax2.set_title("Agent comparison (300 task instances)", fontsize=12)
ax2.set_ylim(0, 88)
ax2.grid(axis="y", alpha=0.3, lw=0.5)
fig.tight_layout()
fig.savefig(out / "rq1_decay_curves.png", bbox_inches="tight")
plt.close(fig)
print("saved", out / "rq1_decay_curves.png")

# Figure 2: A0/A1 completion and representative D-r0 repair cases.
fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.6), dpi=150)
ax = axes[0]
chains = ["C\n(sqlparse)", "D\n(click)"]
a0 = [53.3, 60.6]
a1 = [100.0, 100.0]
x = list(range(len(chains)))
width = 0.34
bars0 = ax.bar([i - width/2 for i in x], a0, width, label="A0 baseline (no protocol)",
               color="#B44B3E")
bars1 = ax.bar([i + width/2 for i in x], a1, width,
               label="A1 intervention (acceptance + repair)", color="#185FA5")
for bars in (bars0, bars1):
    for bar in bars:
        value = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, value + 2, f"{value:.1f}%",
                ha="center", fontsize=11, fontweight="bold")
ax.set_xticks(x)
ax.set_xticklabels(chains)
ax.set_ylim(0, 115)
ax.set_ylabel("Task completion rate, TCR (%)")
ax.set_title("Intervention effect: A0 vs A1\n(3 repetitions per chain)")
ax.grid(axis="y", alpha=0.3, lw=0.5)
ax.legend(fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.18))

ax = axes[1]
cases = ["D4", "D7", "D11"]
before = [11, 12, 8]
after = [0, 0, 0]
x = list(range(len(cases)))
bars_before = ax.bar([i - width/2 for i in x], before, width,
                     label="Before repair (gold-test failures)", color="#B44B3E")
bars_after = ax.bar([i + width/2 for i in x], after, width,
                    label="After repair", color="#6A994E")
for bar, value in zip(bars_before, before):
    ax.text(bar.get_x() + bar.get_width()/2, value + 0.25, str(value),
            ha="center", fontsize=11, fontweight="bold")
for bar in bars_after:
    ax.text(bar.get_x() + bar.get_width()/2, 0.25, "0",
            ha="center", fontsize=10, color="#3B6D11")
ax.set_xticks(x)
ax.set_xticklabels(cases)
ax.set_ylim(0, 13.5)
ax.set_ylabel("Failing gold-test nodes")
ax.set_title("Repair-loop cases (D-r0)\nRejection → feedback → repair → acceptance")
ax.grid(axis="y", alpha=0.3, lw=0.5)
ax.legend(fontsize=9, loc="upper right")
fig.tight_layout()
fig.savefig(out / "rq2_intervention_effect.png", bbox_inches="tight")
plt.close(fig)
print("saved", out / "rq2_intervention_effect.png")
