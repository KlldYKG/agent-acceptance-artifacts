#!/usr/bin/env python3
"""同源/异源合谋对照实验（零 API 成本，A0 存量数据）。

设计：
- 供体（donor）：某 A0 实例 diff 含自写测试文件，且该实例最终 ACCEPT
  （实现正确 → 测试在正确实现上验证过）。
- 受体（impl）：同任务的 A0 REJECT 实例（金测试判定实现是错的）。
- 同源对：受体实现 × 同 agent（可跨 rep）供体测试；异源对：另一 agent。
- 判别力：供体测试跑在受体（坏）实现上；全过 = 合谋，有失败 = 检出。
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

AA = Path("/root/aa")
RUNS = AA / "experiments" / "runs"
REPOS = AA / "dataset" / "repos"
TMP = AA / "experiments" / "_collusion_tmp"
OUT = AA / "experiments" / "_collusion_results.json"

sys.path.insert(0, str(AA / "dataset"))
import gold_check as gc  # noqa: E402

TASK = {t["id"]: t for t in gc.MANIFEST}
TEST_FILE = re.compile(r"^\+\+\+ b/(\S*test\S*\.py)$", re.M)
ADD_DEF = re.compile(r"^\+(?:\s*)def (test_\w+)", re.M)
ADD_CLASS = re.compile(r"^\+(?:\s*)class (Test\w+)", re.M)
# 与 gold_check.py 同口径：各仓库源码布局（PYTHONPATH 需要的相对路径）
SRC_SUBDIR = {"httpx": ["src"], "marshmallow": ["src"], "sqlparse": [],
              "click": ["src"], "black": ["src"]}


def run(cmd, cwd, timeout=120):
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                          timeout=timeout)


def scan_instances():
    """返回 instances[(agent, task, rep)] = dict(accepted, diff_path, test_files)."""
    inst = {}
    for agent in ["opencode", "aider"]:
        for f in sorted(RUNS.glob(
                f"{agent}-deepseek-deepseek-flash-A0-*-r[012]/chain_log.json")):
            run_dir = f.parent
            rep = run_dir.name.rsplit("-r", 1)[1]
            d = json.loads(f.read_text())
            for t in d["tasks"]:
                dp = run_dir / ("task_" + t["task"]) / "diff.patch"
                try:
                    text = dp.read_text(errors="replace")
                except OSError:
                    continue
                inst[(agent, t["task"], rep)] = {
                    "accepted": bool(t["accepted"]),
                    "diff": dp,
                    "test_files": sorted(set(TEST_FILE.findall(text))),
                }
    return inst


def donor_nodes(diff_text, test_files):
    """从供体 diff 提取新增测试的 pytest node id。"""
    nodes = []
    # 按 diff 文件段切分
    parts = re.split(r"^(?=diff --git )", diff_text, flags=re.M)
    for part in parts:
        m = re.search(r"^\+\+\+ b/(\S+)$", part, re.M)
        if not m or m.group(1) not in test_files:
            continue
        path = m.group(1)
        is_new = "--- /dev/null" in part
        cls = None
        for line in part.splitlines():
            if line.startswith("+") and ADD_CLASS.match(line):
                cls = ADD_CLASS.match(line).group(1)
            elif line.startswith("+") and ADD_DEF.match(line):
                name = ADD_DEF.match(line).group(1)
                if is_new or line.startswith("+def ") or line.startswith("+    def "):
                    node = path + "::" + (cls + "::" if cls and (is_new or True) else "")
                    nodes.append(node + name)
    return nodes


def enumerate_pairs(inst):
    pairs = []
    for (agent, task, rep), v in inst.items():
        if v["accepted"] or not v["test_files"]:
            continue  # 受体必须是坏实现
        tinfo = TASK.get(task)
        if tinfo is None:
            continue
        for (dagent, dtask, drep), dv in inst.items():
            if dtask != task or not dv["test_files"] or not dv["accepted"]:
                continue
            kind = "same" if dagent == agent else "cross"
            pairs.append({
                "kind": kind, "impl": (agent, task, rep),
                "donor": (dagent, dtask, drep),
                "repo": tinfo["repo"], "fix": tinfo["fix"],
            })
    return pairs


def execute(pair):
    agent, task, rep = pair["impl"]
    dagent, _, drep = pair["donor"]
    impl_diff = RUNS / f"{agent}-deepseek-deepseek-flash-A0-{task[0]}-r{rep}" / ("task_" + task) / "diff.patch"
    donor_diff = RUNS / f"{dagent}-deepseek-deepseek-flash-A0-{task[0]}-r{drep}" / ("task_" + task) / "diff.patch"
    repo = REPOS / pair["repo"]
    wt = TMP / f"{agent}_{task}_{rep}_x_{dagent}_{drep}"
    res = {"pair": pair, "status": "ok"}
    try:
        run(["git", "worktree", "prune"], repo, timeout=30)
        if wt.exists():
            shutil.rmtree(wt, ignore_errors=True)
        r = run(["git", "worktree", "add", "--detach", str(wt), pair["fix"] + "^"], repo)
        if r.returncode != 0:
            res["status"] = "worktree_fail:" + r.stderr[-120:]
            return res
        # 受体实现：整 diff，但排除供体测试文件（避免冲突）
        cmd = ["git", "apply", "--whitespace=nowarn"]
        for tf in inst_tests(donor_diff):
            cmd += ["--exclude", tf]
        cmd.append(str(impl_diff))
        r = run(cmd, wt)
        if r.returncode != 0:
            res["status"] = "impl_apply_fail:" + r.stderr[-120:]
            return res
        # 供体测试：只应用测试文件
        cmd = ["git", "apply", "--whitespace=nowarn"]
        for tf in inst_tests(donor_diff):
            cmd += ["--include", tf]
        cmd.append(str(donor_diff))
        r = run(cmd, wt)
        if r.returncode != 0:
            res["status"] = "donor_apply_fail:" + r.stderr[-120:]
            return res
        # 提取供体新增测试 node id
        dtext = donor_diff.read_text(errors="replace")
        nodes = donor_nodes(dtext, inst_tests(donor_diff))
        targets = nodes if nodes else inst_tests(donor_diff)
        # 跑测试（PYTHONPATH 与 gold_check 同口径：树[/src]）
        py = AA / "dataset" / "venvs" / pair["repo"] / "bin" / "python"
        pp = os.pathsep.join([str(wt)] + [str(wt / s)
                             for s in SRC_SUBDIR.get(pair["repo"], [])])
        try:
            r = subprocess.run([str(py), "-m", "pytest", *targets, "-q",
                                "--no-header", "-p", "no:cacheprovider"],
                               cwd=str(wt), capture_output=True, text=True,
                               timeout=240, env={"PYTHONPATH": pp, "PATH": "/usr/bin:/bin"})
            out = r.stdout
            if r.returncode == 4 and "error" in (out or "").lower():
                res["status"] = "collection_error:" + (out or r.stderr)[-150:]
                return res
            mpass = re.search(r"(\d+) passed", out)
            mfail = re.search(r"(\d+) failed", out)
            merr = re.search(r"(\d+) error", out)
            res["passed"] = int(mpass.group(1)) if mpass else 0
            res["failed"] = int(mfail.group(1)) if mfail else 0
            res["errors"] = int(merr.group(1)) if merr else 0
            res["collusion"] = (res["failed"] == 0 and res["errors"] == 0
                                and res["passed"] > 0)
            res["nodes"] = len(nodes)
        except subprocess.TimeoutExpired:
            res["status"] = "pytest_timeout"
        return res
    finally:
        run(["git", "worktree", "remove", "--force", str(wt)], repo, timeout=30)
        shutil.rmtree(wt, ignore_errors=True)


def inst_tests(diff_path):
    return sorted(set(TEST_FILE.findall(diff_path.read_text(errors="replace"))))


def main():
    inst = scan_instances()
    pairs = enumerate_pairs(inst)
    print(f"受体候选: {sum(1 for v in inst.values() if not v['accepted'] and v['test_files'])}"
          f" | 供体: {sum(1 for v in inst.values() if v['accepted'] and v['test_files'])}"
          f" | 配对总数 {len(pairs)}", flush=True)
    TMP.mkdir(exist_ok=True)
    results = []
    for i, p in enumerate(pairs):
        r = execute(p)
        results.append(r)
        tag = r.get("status", "ok")
        extra = (f"passed={r.get('passed')} failed={r.get('failed')} "
                 f"collusion={r.get('collusion')}") if tag == "ok" else ""
        print(f"[{i+1}/{len(pairs)}] {p['kind']:5s} {p['impl']} x {p['donor']}"
              f" -> {tag} {extra}", flush=True)
    OUT.write_text(json.dumps(results, indent=1, default=str))
    # 汇总
    for kind in ["same", "cross"]:
        rs = [r for r in results if r["pair"]["kind"] == kind and r["status"] == "ok"]
        col = sum(1 for r in rs if r.get("collusion"))
        print(f"\n{kind}: 有效对 {len(rs)} | 合谋 {col} | 合谋率 "
              f"{col/len(rs)*100:.0f}%" if rs else f"\n{kind}: 0 有效对")


if __name__ == "__main__":
    main()
