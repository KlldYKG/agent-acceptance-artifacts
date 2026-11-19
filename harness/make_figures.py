# -*- coding: utf-8 -*-
"""RQ1-flash 阶段1 成果图：链内序位衰减曲线（opencode）+ 双 agent 对比。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

# opencode 侧各链序位通过数（分子=ACCEPT 次数，分母恒为 3 重复）
POS = {
    "A（httpx）":      {1:3,2:3,3:3,4:3,5:3,6:3,7:3,8:0},
    "B（marshmallow）":{1:3,2:3,3:3,4:3,5:3,6:3,7:3,8:3,9:1,10:1,11:0},
    "C（sqlparse）":   {1:1,2:2,3:0,4:3,5:3,6:1,7:1,8:3,9:2,10:0},
    "D（click）":      {1:3,2:2,3:2,4:1,5:3,6:3,7:0,8:3,9:3,10:0,11:0},
    "E（black）":      {1:3,2:3,3:3,4:0,5:3,6:3,7:3,8:3,9:3,10:3},
}
COLORS = ["#185FA5", "#0F6E56", "#993C1D", "#534AB7", "#3B6D11"]

fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.6), dpi=150,
                         gridspec_kw={"width_ratios": [2.1, 1]})

ax = axes[0]
for (label, pos), c in zip(POS.items(), COLORS):
    xs = sorted(pos)
    ys = [pos[i] / 3 * 100 for i in xs]
    ax.plot(xs, ys, marker="o", ms=4, lw=1.8, color=c, label=label)
ax.set_xlabel("链内任务序位（1 = 链首，最先完成的任务）", fontsize=11)
ax.set_ylabel("通过率（%）", fontsize=11)
ax.set_title("链内任务序位 vs 通过率 —— opencode × DeepSeek-flash × A0 基线（每点 3 次重复）",
             fontsize=12)
ax.set_ylim(-6, 108)
ax.set_xticks(range(1, 12))
ax.grid(alpha=0.3, lw=0.5)
ax.legend(fontsize=9, loc="lower left", framealpha=0.9)
ax.annotate("后段崩溃区", xy=(10.2, 12), fontsize=10, color="#A32D2D")
ax.axvspan(8.5, 11.5, color="#A32D2D", alpha=0.06)

ax2 = axes[1]
names = ["opencode\n（迭代式 agent）", "aider\n（单轮盲改模式）"]
vals = [73.3, 22.7]
bars = ax2.bar(names, vals, width=0.55, color=["#0F6E56", "#993C1D"])
for b, v in zip(bars, vals):
    ax2.text(b.get_x() + b.get_width()/2, v + 2, f"{v:.1f}%",
             ha="center", fontsize=12, fontweight="bold")
ax2.set_ylabel("总体任务通过率 TCR（%）", fontsize=11)
ax2.set_title("双 agent 对比（同一批 300 任务）", fontsize=12)
ax2.set_ylim(0, 88)
ax2.grid(axis="y", alpha=0.3, lw=0.5)

fig.suptitle("")
fig.tight_layout()
import pathlib
out = pathlib.Path(__file__).parent / "figures"
out.mkdir(exist_ok=True)
fig.savefig(out / "rq1_decay_curves.png", bbox_inches="tight")
print("saved", out / "rq1_decay_curves.png")
