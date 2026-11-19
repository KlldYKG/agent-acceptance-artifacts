# -*- coding: utf-8 -*-
"""P2 验收入口：单命令复跑任一任务链（双向有效性验证）。

用法：
  python dataset/run_chain.py            # 复跑全部链（A+B+C）
  python dataset/run_chain.py A          # 只复跑链 A
  python dataset/run_chain.py A C        # 复跑 A 和 C

每任务执行：worktree 展开 fix^ → 覆盖金测试 → 应失败；fix 树 → 应通过。
产出：dataset/gold/report_<chain>.json + 控制台判定表。
明细逻辑见 gold_check.py（含环境噪音豁免清单与自写金测试机制）。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gold_check import MANIFEST, GOLD_DIR, check_task  # noqa: E402

CHAINS = {"A": "httpx 认证→URL→编码", "B": "marshmallow fields→校验器",
          "C": "sqlparse 关键词→切分→格式化", "D": "click 参数→帮助→运行时（放量轮）",
          "E": "black fmt指令→崩溃→行号（放量轮）"}


def main() -> int:
    wanted = [c.upper() for c in sys.argv[1:]] or list(CHAINS)
    unknown = [c for c in wanted if c not in CHAINS]
    if unknown:
        print(f"未知链: {unknown}（可选: {list(CHAINS)}）")
        return 2
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    all_counts: dict[str, int] = {}
    for chain in wanted:
        tasks = [t for t in MANIFEST if t["id"].startswith(chain)]
        print(f"\n===== 链 {chain}：{CHAINS[chain]}（{len(tasks)} 任务）=====")
        results = []
        for t in tasks:
            r = check_task(t)
            results.append(r)
            b, a = r.get("before"), r.get("after")
            bs = f"F{b['failed']}/E{b['errors']}/P{b['passed']}" if b else "n/a"
            as_ = f"F{a['failed']}/E{a['errors']}/P{a['passed']}" if a else "n/a"
            print(f"[{r['id']}] {r['verdict']:<12} {r['fix']} "
                  f"before({bs}) after({as_}) — {r['desc'][:46]}", flush=True)
        (GOLD_DIR / f"report_{chain}.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        for r in results:
            all_counts[r["verdict"]] = all_counts.get(r["verdict"], 0) + 1
    mins = round((time.time() - t0) / 60, 1)
    print(f"\n== 汇总: {all_counts}  耗时 {mins}min")
    ok = all_counts.get("VALID", 0) + all_counts.get("VALID*", 0)
    total = sum(all_counts.values())
    print(f"== 可用任务: {ok}/{total}"
          + ("  ✅ 全部达标" if ok == total else "  ⚠️ 存在待处置任务"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
