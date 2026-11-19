# -*- coding: utf-8 -*-
"""P3 链执行器：实现 DESIGN_CN.md §二 的任务/链语义。

用法：
    python experiments/runner.py --agent aider --model <model> \
        --arm A0 --chain C --rep 1 [--tasks C1,C2] [--dry-run]

- 链状态逐任务携带（缺陷继承的载体）；工作树用临时目录，结束后清理；
- 每 (agent, model, arm, chain, rep) 一个 run 目录，全量原始日志入库；
- A1/A-full 的门控调用使用 PyPI 安装的 agent-acceptance==1.0.0（GATE_PKG_SPEC）。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from adapters import ADAPTERS, get_adapter
import exp_common as ec

ARMS = ("A0", "A1", "A-full")


# ----------------------------------------------------------------- 门控调用

def gate_venv() -> Path:
    """惰性创建实验门控 venv（PyPI 安装 GATE_PKG_SPEC，锁定 C1 冻结版）。"""
    vdir = ec.WS / "experiments" / "venvs" / "gate"
    exe = vdir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not exe.exists():
        print("[gate] creating gate venv ...", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(vdir)], check=True)
        subprocess.run([str(exe), "-m", "pip", "install", "-q", ec.GATE_PKG_SPEC],
                       check=True)
    return exe


def run_gate(tree: Path, base: str, head: str, out_dir: Path, task: dict) -> dict | None:
    """对 agent 的改动跑 agent-acceptance（有效性验证 [+ 变异]）。

    返回 evidence.json 内容；无测试改动（NO_EVIDENCE）返回 None。
    """
    vp = gate_venv()
    cmd = [str(vp), "-m", "agent_acceptance.cli", "run",
           "--repo", str(tree), "--base", base, "--head", head,
           "--python", str(ec.gc.VENV(task["repo"])),
           "--out", str(out_dir)]
    if "full" in task.get("_arm", ""):
        cmd += ["--mutation-budget", "300"]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    ev = out_dir / "evidence.json"
    if not ev.exists():
        return {"gate_error": (p.stdout or "") + (p.stderr or "")}
    data = json.loads(ev.read_text(encoding="utf-8"))
    if data.get("verdict") == "NO_EVIDENCE":
        return None
    return data


def evidence_summary(ev: dict | None, arm: str) -> str:
    """给 agent 的证据判定摘要（A1）；A-full 追加幸存突变报告。"""
    if not ev:
        return ("The acceptance tool found NO test-evidence in your change: you "
                "did not add or modify any tests. A contribution needs tests that "
                "actually pin the new behavior.")
    lines = [f"Evidence strength: {ev.get('strength')} (verdict {ev.get('verdict')})"]
    for t in ev.get("tests", []):
        lines.append(f"- {t.get('name')}: {t.get('classification')}")
    if "full" in arm:
        m = ev.get("mutation") or {}
        if m.get("status") == "OK":
            lines.append(f"Mutation sampling: score={m.get('score')} "
                         f"(killed {m.get('killed')}, survived {m.get('survived')})")
            for s in (m.get("survivor_samples") or [])[:5]:
                lines.append(f"  surviving mutant (behavior NOT pinned by your tests): {s}")
        else:
            lines.append(f"Mutation sampling: {m.get('status')} (no numeric claims)")
    return "\n".join(lines)


# ----------------------------------------------------------------- prompt

def task_prompt(task: dict, workdir: Path | None = None) -> str:
    where = f" at {workdir}" if workdir else ""
    return (
        f"You are contributing a small change to the Python project in the "
        f"current working directory ({task['repo']}){where}.\n\n"
        f"Task: {task['desc']}.\n\n"
        "Requirements:\n"
        "1. Modify the project source code to implement the change.\n"
        "2. Add or update tests that cover the new behavior, like a real "
        "contributor would.\n"
        "3. Edit files in place; do NOT run git commit or git push.\n"
        "4. Keep the change minimal and focused on this task.\n"
    )


def repair_prompt(task: dict, gold: dict, ev: dict | None, arm: str) -> str:
    fails = "\n".join(f"- {n}" for n in gold["fail_nodes"]) or "- (no specific node)"
    return (
        "Your previous change did NOT pass the project's acceptance tests.\n\n"
        f"Failing acceptance tests:\n{fails}\n\n"
        f"Deterministic evidence check of your own tests:\n"
        f"{evidence_summary(ev, arm)}\n\n"
        "Revise the implementation in the current working directory so the "
        "behavior is correct and your tests genuinely pin it. Do NOT run "
        "git commit.\n"
    )


# ----------------------------------------------------------------- 执行

def commit_tree(repo: Path, msg: str) -> tuple[bool, str]:
    """提交工作树全部改动（detached HEAD），返回 (有无改动, 新提交)。"""
    ec.gc.git(repo, "add", "-A")
    code, out = ec.gc.git(repo, "diff", "--cached", "--quiet")
    if code == 0:
        return False, ec.gc.git(repo, "rev-parse", "HEAD")[1].strip()
    ec.gc.git(repo, "-c", "user.email=exp@example.com", "-c", "user.name=exp",
              "commit", "-qm", msg)
    return True, ec.gc.git(repo, "rev-parse", "HEAD")[1].strip()


def run_chain(agent: str, model: str, arm: str, chain: str, rep: int,
              only_tasks: list[str] | None = None, dry_run: bool = False) -> Path:
    tasks = ec.chain_tasks(chain)
    if only_tasks:
        tasks = [t for t in tasks if t["id"] in only_tasks]
    assert tasks, f"no tasks for chain {chain}"
    repos = {t["repo"] for t in tasks}
    assert len(repos) == 1, f"chain spans repos: {repos}"
    repo = ec.gc.REPOS / tasks[0]["repo"]

    run_dir = ec.new_run_dir(agent, model, arm, chain, rep)
    print(f"[run] {run_dir.name} ({len(tasks)} tasks)", flush=True)

    base_ref = f"{tasks[0]['fix']}^"
    tmp = Path(tempfile.mkdtemp(prefix=f"exp_{run_dir.name}_"))
    meta = {
        "run_id": run_dir.name, "agent": agent, "model": model, "arm": arm,
        "chain": chain, "rep": rep, "base_ref": base_ref,
        "gate_pkg": ec.GATE_PKG_SPEC, "python": sys.version.split()[0],
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    ec.write_meta(run_dir, **meta)
    if dry_run:
        for t in tasks:
            print(f"  would run {t['id']}: {t['desc']}")
        shutil.rmtree(tmp, ignore_errors=True)
        return run_dir

    adapter = get_adapter(agent)
    tree = tmp / "tree"
    code, out = ec.gc.git(repo, "worktree", "add", "--detach", str(tree), base_ref)
    assert code == 0, f"worktree failed: {out[-300:]}"
    # opencode（V1）把项目根解析到 git 主仓库（git common dir），临时 worktree
    # 内一切路径都判 external_directory 并在无头模式自动拒绝（实测三轮，配置
    # 文件在 worktree 根也不生效）。改为独立仓库：摘掉 worktree 指针、就地
    # git init，项目根 = 任务树本身。内容与 base_ref 完全一致，基线单独成
    # 提交，后续 commit/diff/gate 全在本仓库内进行。
    (tree / ".git").unlink()
    assert ec.gc.git(tree, "init", "-q")[0] == 0, "tree git init failed"
    ec.bootstrap_tree(tasks[0]["repo"], tree)
    ec.gc.git(tree, "add", "-A")
    # agent 本地产物不进候选 diff（.git/info/exclude 只在本地生效，不污染提交）
    excl = tree / ".git" / "info" / "exclude"
    excl.parent.mkdir(parents=True, exist_ok=True)
    excl.write_text(".aider.*\n.opencode\nopencode.json\n", encoding="utf-8")
    ec.gc.git(tree, "-c", "user.email=exp@example.com", "-c", "user.name=exp",
              "commit", "-qm", f"baseline {base_ref}")
    state_head = ec.gc.git(tree, "rev-parse", "HEAD")[1].strip()

    chain_log = {"run_id": run_dir.name, "tasks": []}
    try:
        for t in tasks:
            tid = t["id"]
            tdir = run_dir / f"task_{tid}"
            tdir.mkdir(exist_ok=True)
            tlog: dict = {"task": tid, "desc": t["desc"], "rounds": []}

            accepted, gold, ev = False, None, None
            for rnd in (1, 2):
                prompt = (task_prompt(t, tree) if rnd == 1 else repair_prompt(
                    t, gold, ev, arm))
                ar = adapter.run(tree, prompt, model, ec.AGENT_TIMEOUT_S,
                                 log_path=tdir / f"transcript_r{rnd}.log")
                (tdir / f"transcript_r{rnd}.txt").write_text(
                    ar.to_json() + "\n---- TRANSCRIPT ----\n" + ar.transcript,
                    encoding="utf-8")
                changed, cand = commit_tree(tree, f"exp {tid} round {rnd}")
                ec.overlay_gold(tree, repo, t)   # 评测前放入金测试（fix 版）
                gold = ec.eval_gold(tree, t)
                ec.remove_gold(tree, t)          # 评测后移除（防泄漏给 agent）
                ev = None
                if arm != "A0" and changed:
                    ev = run_gate(tree, state_head, cand, tdir / f"gate_r{rnd}",
                                  {**t, "_arm": arm})
                tlog["rounds"].append({
                    "round": rnd, "adapter": {k: v for k, v in ar.__dict__.items()
                                              if k != "transcript"},
                    "committed": changed, "candidate": cand,
                    "gold": {k: v for k, v in gold.items() if k != "raw_tail"},
                    "gate_verdict": (ev or {}).get("verdict") if ev else None,
                })
                accepted = gold["ok"]
                if accepted or arm == "A0":
                    break
                if not changed and rnd == 1:
                    break  # agent 没产出任何改动，修复轮无意义
            (tdir / "gold_result.json").write_text(
                json.dumps(gold, indent=2, ensure_ascii=False), encoding="utf-8")
            if ev:
                (tdir / "gate_summary.txt").write_text(
                    evidence_summary(ev, arm), encoding="utf-8")
            code, diff = ec.gc.git(tree, "diff", f"{state_head}", "HEAD")
            (tdir / "diff.patch").write_text(diff, encoding="utf-8")
            tlog["accepted"] = accepted
            chain_log["tasks"].append(tlog)
            state_head = ec.gc.git(repo, "rev-parse", "HEAD")[1].strip()
            print(f"  [{tid}] {'ACCEPT' if accepted else 'REJECT'} "
                  f"(gold F{gold['counts']['failed']}/E{gold['counts']['errors']}"
                  f"/P{gold['counts']['passed']})", flush=True)
            (run_dir / "chain_log.json").write_text(
                json.dumps(chain_log, indent=2, ensure_ascii=False),
                encoding="utf-8")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # 独立仓库，整目录直接删
        meta["ended"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        ec.write_meta(run_dir, **meta)

    n_ok = sum(1 for x in chain_log["tasks"] if x["accepted"])
    print(f"[done] {run_dir.name}: {n_ok}/{len(chain_log['tasks'])} accepted",
          flush=True)
    return run_dir


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, choices=sorted(ADAPTERS))
    ap.add_argument("--model", required=True)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--chain", required=True)
    ap.add_argument("--rep", type=int, default=1)
    ap.add_argument("--tasks", default=None, help="逗号分隔任务 ID 子集")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    only = [x.strip() for x in a.tasks.split(",")] if a.tasks else None
    run_chain(a.agent, a.model, a.arm, a.chain, a.rep, only, a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
