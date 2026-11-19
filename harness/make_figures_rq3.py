# -*- coding: utf-8 -*-
"""RQ3 消融成果图：A1 vs A-full 头对头 + 变异触达漏斗 + 变异预算敏感度。

数据来源（全部为实测，溯源见 paper/DRAFT_EN.md 附录 A）：
- 头对头：A-full 重跑批(_batch_s3b.log) vs 阶段2 A1 批(_batch_a1.log)，各 6 runs/63 任务
- 漏斗：A-full 重跑批 63 任务的 evidence.json 全量扫描
- 预算敏感度：C4 离线冒烟（sqlparse，_smoke_mut_full.log + diag 记录）
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

GREEN = "#0F6E56"
BLUE = "#185FA5"
RUST = "#993C1D"
GRAY = "#7A7A7A"
AMBER = "#C07A00"

fig, axes = plt.subplots(1, 3, figsize=(14.5, 4.8), dpi=150,
                         gridspec_kw={"width_ratios": [1.15, 1.25, 1.05]})

# ---------------- Panel 1: A1 vs A-full 头对头 ----------------
ax = axes[0]
metrics = ["TCR\n(任务通过率)", "修复任务数", "总轮数", "agent 成本\n($)"]
a1 = [100, 21, 84, 0.885]
af = [100, 20, 83, 0.795]
# 归一化到各自量纲内画分组条形（TCR 用 0-110 刻度展示）
xmax = [110, 26, 100, 1.05]
for i, (m, x1, x2, xm) in enumerate(zip(metrics, a1, af, xmax)):
    y = i
    ax.barh(y + 0.18, x1, height=0.32, color=BLUE,
            label="A1（金测试验收）" if i == 0 else None)
    ax.barh(y - 0.18, x2, height=0.32, color=GREEN,
            label="A-full（+变异相）" if i == 0 else None)
    ax.text(x1 + xm * 0.02, y + 0.18, f"{x1:g}", va="center", fontsize=9.5, color=BLUE)
    ax.text(x2 + xm * 0.02, y - 0.18, f"{x2:g}", va="center", fontsize=9.5, color=GREEN)
ax.set_yticks(range(len(metrics)))
ax.set_yticklabels(metrics, fontsize=10)
ax.invert_yaxis()
ax.set_xlim(0, 118)
ax.set_title("(a) 头对头：A-full vs A1\n（各 6 runs × 63 任务，opencode × flash）", fontsize=11)
ax.grid(axis="x", alpha=0.3, lw=0.5)
ax.legend(fontsize=8.5, loc="lower right", framealpha=0.9)
ax.text(0.5, -0.34, "TCR 维度增量 = 0（天花板）；其余差异在噪声级",
        fontsize=9, color=GRAY, ha="center", transform=ax.transAxes)

# ---------------- Panel 2: 变异触达漏斗 ----------------
ax = axes[1]
stages = [
    ("63 任务\n（A-full 批全部）", 63, BLUE),
    ("6 任务产出测试文件（9.5%）", 6, BLUE),
    ("3 × TIMEOUT\n（C1：800+ 突变体 / 300s 预算）", 3, AMBER),
    ("3 × 基线阻断\n（D1：agent 破损测试顶停 mutmut）", 3, RUST),
    ("批内变异分数：0", 0, GRAY),
]
widths = [s[1] for s in stages]
maxw = max(widths)
for i, (label, w, c) in enumerate(stages):
    left = (maxw - w) / 2 if w > 0 else maxw * 0.42
    ax.barh(i, max(w, 0.6), left=left, height=0.62, color=c, alpha=0.88)
    ax.text(maxw / 2, i, f"{w}", ha="center", va="center",
            fontsize=11, fontweight="bold", color="white" if w > 0 else GRAY)
    ax.text(maxw * 1.03, i, label, ha="left", va="center", fontsize=8.6)
    if i < len(stages) - 1:
        ax.annotate("", xy=(maxw / 2, i + 0.78), xytext=(maxw / 2, i + 0.28),
                    arrowprops=dict(arrowstyle="-|>", color=GRAY, lw=1.2))
ax.set_xlim(0, maxw * 2.05)
ax.set_ylim(-0.55, len(stages) - 0.3)
ax.invert_yaxis()
ax.axis("off")
ax.set_title("(b) 变异触达漏斗：三层约束\n（批内分数产出 = 0/63）", fontsize=11)

# ---------------- Panel 3: 预算敏感度 ----------------
ax = axes[2]
budgets = ["150s", "300s\n(CI 预算)", "900s"]
scores = [None, None, 1.0]
colors = [AMBER, AMBER, GREEN]
labels = ["TIMEOUT", "TIMEOUT", "OK\nscore = 1.0"]
bars = ax.bar(budgets, [1, 1, 1], width=0.58, color=colors, alpha=0.88)
for b, lab in zip(bars, labels):
    ax.text(b.get_x() + b.get_width() / 2, 0.5, lab, ha="center", va="center",
            fontsize=10.5, fontweight="bold", color="white")
ax.annotate("killed = 874, survived = 0\n（885s 实际用时，≈1 突变体/s）",
            xy=(2, 1.0), xytext=(0.28, 1.24), fontsize=9,
            arrowprops=dict(arrowstyle="-|>", color=GRAY, lw=1.1), color=GREEN)
ax.text(0.5, 1.10, "诚实降级：不伪造分数", fontsize=9.5, color=AMBER, ha="center",
        fontweight="bold")
ax.set_ylim(0, 1.52)
ax.set_yticks([])
ax.set_xlabel("变异相预算（C4 离线冒烟，sqlparse）", fontsize=10)
ax.set_title("(c) 预算敏感度\n（300s 不可行 → 900s 完整且零幸存者）", fontsize=11)
for spine in ["top", "right", "left"]:
    ax.spines[spine].set_visible(False)

import pathlib
out = pathlib.Path(__file__).parent / "figures"
out.mkdir(exist_ok=True)
fig.tight_layout()
fig.savefig(out / "rq3_ablation.png", bbox_inches="tight")
print("saved", out / "rq3_ablation.png")
