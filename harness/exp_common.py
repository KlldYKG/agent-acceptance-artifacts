# -*- coding: utf-8 -*-
"""P3 实验公共层：复用 dataset/gold_check.py 的清单与机制，不复制逻辑。

单一事实源 = dataset/gold_check.py 的 MANIFEST（链/任务/fix 哈希）。
本模块提供：金测试提取、agent 工作树上的金测试评测（含噪音豁免）、
日志目录约定。实验语义见 experiments/DESIGN_CN.md。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WS / "dataset"))

import gold_check as gc  # noqa: E402  (dataset/gold_check.py)

RUNS = WS / "experiments" / "runs"
# 实验锁定的门控工具版本（C1 冻结版；变更须 ADR + DESIGN 回写）
GATE_PKG_SPEC = "agent-acceptance==1.0.0"
AGENT_TIMEOUT_S = 1800  # 单次 agent 运行墙钟上限
GOLD_EVAL_TIMEOUT_S = 900


def chain_tasks(chain_id: str) -> list[dict]:
    """链 = MANIFEST 中同前缀任务，按清单顺序（已按上游时间排序）。"""
    return [t for t in gc.MANIFEST if t["id"].startswith(chain_id)]


def gold_for_task(task: dict) -> list[str]:
    """金测试文件：自写金测试优先，否则 fix 自带测试文件。"""
    authored = gc.AUTHORED_GOLD.get(task["id"])
    if authored:
        return [authored[0]]
    return gc.changed_test_files(gc.REPOS / task["repo"], task["fix"])


def gold_targets(task: dict) -> list[str]:
    authored = gc.AUTHORED_GOLD.get(task["id"])
    if authored:
        return [authored[0]]
    return gc.build_targets(task["repo"], gc.changed_test_files(
        gc.REPOS / task["repo"], task["fix"]))


def git_out(repo: Path, *args: str, timeout: int = 300) -> tuple[int, str]:
    return gc.git(repo, *args, timeout=timeout)


def bootstrap_tree(repo_name: str, tree: Path) -> None:
    """注入打包期生成模块等 bootstrap 文件（如 black 的 _black_version.py）。"""
    for rel, content in gc.REPO_BOOTSTRAP_FILES.get(repo_name, {}).items():
        (tree / rel).write_text(content, encoding="utf-8")


def fix_file_content(repo: Path, ref: str, rel: str) -> bytes | None:
    """从仓库对象库直接取某 ref 下的文件内容（字节级，不落 worktree）。"""
    p = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{rel}"],
                       capture_output=True, timeout=60)
    if p.returncode != 0:
        return None
    return p.stdout


def overlay_gold(tree: Path, repo: Path, task: dict) -> list[str]:
    """把金测试文件（fix 版内容）覆盖进 agent 工作树，返回覆盖清单。"""
    authored = gc.AUTHORED_GOLD.get(task["id"])
    if authored:
        src = gc.GOLD_DIR / "authored" / f"{task['id']}.py"
        dst = tree / authored[0]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return [authored[0]]
    copied = []
    for rel in gc.changed_test_files(repo, task["fix"]):
        content = fix_file_content(repo, task["fix"], rel)
        if content is None:
            continue
        dst = tree / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(content)  # git show 输出经文本解码会破坏二进制；测试均为文本
        copied.append(rel)
    return copied


def eval_gold(tree: Path, task: dict) -> dict:
    """在 agent 工作树上跑金测试（噪音豁免同 gold_check），不修改树内容判定。

    返回 {ok, counts, fail_nodes, noise_nodes, seconds}。调用方负责评测后
    把金测试文件从树里删掉（防泄漏给后续任务的 agent）。
    """
    targets = gold_targets(task)
    code, res, out = gc.pytest_run(gc.VENV(task["repo"]), tree, targets, task["repo"])
    fail_nodes = res.get("fail_nodes", [])
    noise = [n for n in fail_nodes if any(k in n for k in gc.KNOWN_NOISE_NODES)]
    real_fail = [n for n in fail_nodes if n not in noise]
    ok = not real_fail and (res["passed"] > 0 or res["skipped"] > 0)
    return {
        "ok": ok, "counts": {k: res[k] for k in ("passed", "failed", "errors", "skipped")},
        "fail_nodes": real_fail, "noise_nodes": noise, "seconds": None,
        "raw_tail": out[-2000:] if not ok else "",
    }


def remove_gold(tree: Path, task: dict) -> None:
    """评测后删除金测试文件（防信息泄漏给 agent 的后续任务）。"""
    for rel in gold_for_task(task):
        f = tree / rel
        if f.exists():
            f.unlink()


def new_run_dir(agent: str, model: str, arm: str, chain: str, rep: int) -> Path:
    safe_model = model.replace("/", "-")  # 模型名可能带 provider 前缀（deepseek/xxx）
    run_id = f"{agent}-{safe_model}-{arm}-{chain}-r{rep}"
    d = RUNS / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "transcripts").mkdir(exist_ok=True)
    return d


def write_meta(run_dir: Path, **kw) -> None:
    (run_dir / "meta.json").write_text(
        json.dumps(kw, indent=2, ensure_ascii=False), encoding="utf-8")


def now() -> float:
    return time.time()
