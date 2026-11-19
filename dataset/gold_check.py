# -*- coding: utf-8 -*-
"""P2 步骤③：金标准测试提取 + 双向有效性验证（狗粮阶段）。

对 manifest 中每个任务（= 一个 fix commit）：
  1. `git diff --name-only fix^ fix -- <test_dirs>` 提取该 fix 涉及的测试文件（金测试）；
  2. worktree 展开 fix^ 树，把 fix 版测试文件覆盖进去（overlay 语义，与 agent-acceptance 相同）；
  3. fail-before：在 fix^ 树上只跑金测试 → 期望至少 1 个失败（证明测试有区分度）；
  4. pass-after：在 fix 树上跑同样测试 → 期望全过（证明金测试定义的行为已实现）。

判定：VALID / PRE-PASS（base 也过，无区分度）/ BROKEN_GOLD（base 收集错误等非断言失败，
需人工看）/ NO_TESTS（fix 未带测试，需自authoring）。

导入机制：venv 中已卸载项目包的可编辑安装，靠 PYTHONPATH=<树>[/src] 导入当前树代码，
保证跑的是钉点版本而非 HEAD 目录（可编辑安装的 meta-finder 会穿透 PYTHONPATH，必须卸载）。

用法：python dataset/gold_check.py [chain ...]   # 默认全跑
输出：dataset/gold/report.json + 控制台摘要
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
REPOS = WS / "dataset" / "repos"
import os as _os
VENV = lambda name: WS / "dataset" / "venvs" / name / (  # noqa: E731
    "Scripts/python.exe" if _os.name == "nt" else "bin/python")
GOLD_DIR = WS / "dataset" / "gold"

TEST_DIRS = ["tests", "test"]
# 各仓库源码布局：PYTHONPATH 需要的相对路径
SRC_SUBDIR = {"httpx": ["src"], "marshmallow": ["src"], "sqlparse": [],
              "click": ["src"], "black": ["src"]}

MANIFEST: list[dict] = [
    # 链 A：httpx（2026-11-16 修订：A3 重构提交无区分测试 → 换 7c0cda1；A8 纯测试提交 → 换 6d852d3）
    *[
        {"id": f"A{i}", "repo": "httpx", "fix": sha, "issue": issue, "desc": desc}
        for i, (sha, issue, desc) in enumerate([
            ("99cba6a", "digest-rfc2069", "Fix RFC 2069 mode digest authentication"),
            ("6d852d3", "3116", "Fix client.send() timeout new Request instance"),
            ("7c0cda1", "PR3250", "Improve InvalidURL error message"),
            ("49d74a2", "3313", "Clarified error when header value is None"),
            ("d293374", "PR3371", "Review URL percent escaping sets (WHATWG)"),
            ("ba2e512", "PR3373/3413", "urlescape + behavior for form spaces"),
            ("5dda2aa", "PR3376", "default safe characters for urlescape"),
            ("9fd6f0c", "3363", "Ensure JSON representation is compact"),
        ], start=1)
    ],
    # 链 B：marshmallow
    *[
        {"id": f"B{i}", "repo": "marshmallow", "fix": sha, "issue": issue, "desc": desc}
        for i, (sha, issue, desc) in enumerate([
            ("39e7c833", "2891", "ValidationError with uppercase file URLs [fix 8dc078e2+测试 c62b9113，经合并提交提取]"),
            ("fea54285", "2925", "Make Number and Mapping abstract base classes"),
            ("19ca8dce", "2868", "Fix Constant field rejecting None during load"),
            ("070dde08", "2900/2915", "Fix Constant required=True ValueError"),
            ("65374df0", "2869", "Fix OneOf.options() phantom entries"),
            ("252090c7", "PR2903", "Fix nested partial prefix attr_name vs data_key"),
            ("024b5d09", "PR2902", "Fix Enum by-name lookup to actual members"),
            ("72ac4a04", "PR2904", "Reject booleans in from_timestamp_ms"),
            ("f07eadc8", "2936", "Email validator IDN support"),
            ("902f99c4", "PR3016", "URL validator fragment after empty path"),
            ("5761beab", "pluck", "Fix Pluck handling of empty data_key"),
        ], start=1)
    ],
    # 链 C：sqlparse
    *[
        {"id": f"C{i}", "repo": "sqlparse", "fix": sha, "issue": issue, "desc": desc}
        for i, (sha, issue, desc) in enumerate([
            ("6b05583", "682", "Recognize -> as single operator"),
            ("791e25d", "784", "Split CASE clauses within BEGIN block"),
            ("0c4902f", "782", "CTE formatting idempotency (whitespace)"),
            ("e48000a", "785", "Add EXTENSION keyword"),
            ("73c8ba3", "801", "strip_comments removes comment-only statements"),
            ("1a3bfbd", "809", "Semicolons inside BEGIN...END not split"),
            ("5ca50a2", "826", "BEGIN TRANSACTION split regression"),
            ("da67ac1", "827", "DoS protection raises SQLParseError"),
            ("8f978ca", "845", "Stack-based splitter for FOR/IF/WHILE blocks"),
            ("ac3b9e0", "752", "Recognize MATERIALIZED as keyword [金测试自写：authored]"),
        ], start=1)
    ],
    # 链 D：click（放量轮，2026-11-16 新增；统一取 PR 合并提交以包含测试）
    *[
        {"id": f"D{i}", "repo": "click", "fix": sha, "issue": issue, "desc": desc}
        for i, (sha, issue, desc) in enumerate([
            ("051bb0f", "gc-stdout", "Do not let the GC close a borrowed stdout"),
            ("09195f6", "3578", "Fix double-bracketing of choices in synopsis"),
            ("7a16b20", "3582", "Fix package_name resolution module vs distribution"),
            ("3495fba", "collide", "Warn when an argument name collides with other parameters"),
            ("07c909f", "style-color", "Validate style() color arguments"),
            ("b67832c", "3678", "Fix parsing when a parameter is named help"),
            ("fc5c7f4", "3764", "Fix error reporting on Windows when error raised in pager"),
            ("4295457", "3805", "Fix copy/deepcopy/pickle of Sentinel members"),
            ("00f257b", "3818", "Fix race condition on KeyboardInterrupt in main()"),
            ("7068985", "3865", "Fix short help abbreviation"),
            ("8c73ff1", "3884", "Fix show_envvar output for sequence/empty envvar"),
        ], start=1)
    ],
    # 链 E：black（放量轮，2026-11-16 新增；fmt 指令边界→崩溃→行号，取 PR 合并提交）
    *[
        {"id": f"E{i}", "repo": "black", "fix": sha, "issue": issue, "desc": desc}
        for i, (sha, issue, desc) in enumerate([
            ("2f0b4078", "5643", "fmt:off region ends at a closing bracket"),
            ("19b0ad66", "5651", "fmt:off before the trailing comma in brackets"),
            ("a755b562", "5647", "fmt:skip on last line of multiline conditional"),
            ("b1c244db", "5650", "Line numbers in parse errors with leading blank lines"),
            ("58fc8385", "5671", "Skipped async def header with ... body"),
            ("86b8a3b3", "5678", "Async statements dropped after comment-only fmt block"),
            ("36fdb516", "5674", "fmt:skip on semicolon-separated body on own line"),
            ("741cab16", "5681", "Crash on backslash-only lines in untouched code"),
            ("0b2b5e59", "5664", "Reject non-positive --line-length values"),
            ("4724f13b", "5662", "Crash on commented parenthesized assignment target"),
        ], start=1)
    ],
]
# 自写金测试（上游 fix 未带测试的任务）：文件放 dataset/gold/authored/<id>.py，
# 验证时覆盖到 base/head 两棵树的 tests/ 下。
AUTHORED_GOLD: dict[str, tuple[str, str]] = {
    # id -> (仓库内测试路径, 仓库 test_dirs 根)
    "C4": ("tests/test_extension_keyword.py", "tests"),
    "E9": ("tests/test_line_length_validation.py", "tests"),
}

# 数据驱动测试仓库：fix 只加数据用例文件（非 test_ 模块），pytest 目标须是
# 主测试文件 + 参数化节点 ID，否则 pytest 会把数据文件当模块收集而报错。
# repo -> {数据根, 子目录 -> 测试函数}
DATA_CASE_DIRS: dict[str, dict] = {
    "black": {
        "data_root": "tests/data",
        "subdir_tests": {
            "cases": "test_simple_format",
            "line_ranges_formatted": "test_line_ranges_line_by_line",
        },
        "main": "tests/test_format.py",
    },
}


def build_targets(repo: str, gold: list[str]) -> list[str]:
    """把金测试文件列表转成 pytest 目标：测试模块直接跑；数据用例走精确节点 ID。"""
    spec = DATA_CASE_DIRS.get(repo)
    if not spec:
        return [f for f in gold if Path(f).name.startswith("test_")]
    modules = [f for f in gold
               if Path(f).name.startswith("test_") and not f.startswith(spec["data_root"])]
    targets = list(modules)
    for f in gold:
        if not f.startswith(spec["data_root"]):
            continue
        rel = Path(f)
        rel_parts = rel.parts  # ("tests","data",<subdir>,<name>.py)
        if len(rel_parts) >= 4 and rel_parts[2] in spec["subdir_tests"]:
            func = spec["subdir_tests"][rel_parts[2]]
            targets.append(f'{spec["main"]}::{func}[{rel.stem}]')
        else:
            targets.append(spec["main"])
    # 去重保持顺序
    seen, out = set(), []
    for t in targets:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


# 打包期生成的模块（hatch 构建钩子产物，源码树没有）——验证前注入树根。
REPO_BOOTSTRAP_FILES: dict[str, dict[str, str]] = {
    "black": {"_black_version.py": 'version = "0.0.0"\n'},
}

# 环境噪音豁免清单（2026-11-16 Windows 实测定性，见 GOLD_VALIDATION_CN.md §二）：
# 这些节点在 fix 树失败与任务修复无关，判 VALID*（VALID_WITH_NOISE）。
# harness 正式化时应按平台注入（Windows 专用）。
KNOWN_NOISE_NODES: list[str] = [
    "test_download",                                  # pytest isolated_filesystem DeprecationWarning
    "test_write_timeout[trio]",                       # Windows 计时敏感（httpx 全套已知）
    "test_from_timestamp_with_overflow_value",        # marshmallow #2999 Windows 消息差异
    "test_multipart_encode_files_raises_exception_with_text_mode_file",  # Windows 文本模式
]


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None,
        timeout: int = 1200) -> tuple[int, str]:
    import os
    full_env = {**os.environ, **env} if env else None
    try:
        p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=full_env,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return p.returncode, (p.stdout or "") + "\n" + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"


def git(repo: Path, *args: str, timeout: int = 300) -> tuple[int, str]:
    return run(["git", *args], cwd=repo, timeout=timeout)


def changed_test_files(repo: Path, fix: str) -> list[str]:
    code, out = git(repo, "diff", "--name-only", f"{fix}^", fix, "--", *TEST_DIRS)
    if code != 0:
        return []
    return [l.strip() for l in out.splitlines() if l.strip().endswith(".py")]


def parse_results(out: str) -> dict:
    """从 pytest -q 输出提取计数与失败节点。"""
    res = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "fail_nodes": []}
    m = re.search(r"=+\s*(.+?)\s+in\s+[\d.]+s", out)
    tail = out.strip().splitlines()[-1] if out.strip() else ""
    for line in out.splitlines():
        if re.match(r"^(FAILED|ERROR)\s", line.strip()):
            res["fail_nodes"].append(line.strip())
    summary = m.group(1) if m else tail
    for key, pat in [("passed", r"(\d+) passed"), ("failed", r"(\d+) failed"),
                     ("errors", r"(\d+) error"), ("skipped", r"(\d+) skipped")]:
        mm = re.search(pat, summary)
        if mm:
            res[key] = int(mm.group(1))
    if "no tests ran" in summary:
        res["passed"] = 0
    return res


def pytest_run(vp: Path, cwd: Path, targets: list[str], label: str) -> tuple[int, dict, str]:
    pp = os_pathsep_join(cwd, SRC_SUBDIR.get(label, []))
    code, out = run([str(vp), "-m", "pytest", "-q", "--no-header",
                     "-p", "no:cacheprovider", *targets],
                    cwd=cwd, env={"PYTHONPATH": pp}, timeout=900)
    return code, parse_results(out), out


def os_pathsep_join(root: Path, subdirs: list[str]) -> str:
    import os
    parts = [str(root)] + [str(root / s) for s in subdirs]
    return os.pathsep.join(parts)


def check_task(task: dict) -> dict:
    repo = REPOS / task["repo"]
    fix = task["fix"]
    vp = VENV(task["repo"])
    r = {**task, "verdict": "?", "gold_files": [], "before": None, "after": None}

    # 1. 金测试 = fix 涉及的测试文件，或自写金测试
    authored = AUTHORED_GOLD.get(task["id"])
    authored_src = GOLD_DIR / "authored" / f"{task['id']}.py"
    if authored:
        gold = [authored[0]]
    else:
        gold = changed_test_files(repo, fix)
    r["gold_files"] = gold
    if not gold:
        r["verdict"] = "NO_TESTS"
        return r
    if authored and not authored_src.exists():
        r["verdict"] = "AUTHORED_MISSING"
        return r

    tmp = Path(tempfile.mkdtemp(prefix=f"gold_{task['id']}_"))
    try:
        # 2. fix 树 → pass-after（自写金测试需先放入；普通任务的 fix 自带）
        code, out = git(repo, "worktree", "add", "--detach", str(tmp / "head"), fix)
        if code != 0:
            r["verdict"] = "GIT_ERROR"
            r["note"] = out[-200:]
            return r
        if authored:
            dst = tmp / "head" / gold[0]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(authored_src, dst)
        for rel, content in REPO_BOOTSTRAP_FILES.get(task["repo"], {}).items():
            (tmp / "head" / rel).write_text(content, encoding="utf-8")
        t0 = time.time()
        code_a, res_a, out_a = pytest_run(vp, tmp / "head", build_targets(task["repo"], gold), task["repo"])
        r["after"] = {**res_a, "seconds": round(time.time() - t0, 1)}

        # 3. fix^ 树 + overlay 金测试 → fail-before
        code, out = git(repo, "worktree", "add", "--detach", str(tmp / "base"), f"{fix}^")
        if code != 0:
            r["verdict"] = "GIT_ERROR"
            r["note"] = out[-200:]
            return r
        for f in gold:  # base 树统一从 head 树取（对普通任务即 fix 版；对 authored 已放入 head）
            dst = tmp / "base" / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tmp / "head" / f, dst)
        for rel, content in REPO_BOOTSTRAP_FILES.get(task["repo"], {}).items():
            (tmp / "base" / rel).write_text(content, encoding="utf-8")
        t0 = time.time()
        code_b, res_b, out_b = pytest_run(vp, tmp / "base", build_targets(task["repo"], gold), task["repo"])
        r["before"] = {**res_b, "seconds": round(time.time() - t0, 1)}

        # 4. 判定
        after_fail_nodes = r["after"].get("fail_nodes", [])
        unexplained = [n for n in after_fail_nodes
                       if not any(k in n for k in KNOWN_NOISE_NODES)]
        after_ok = not unexplained \
            and (r["after"]["passed"] > 0 or r["after"]["skipped"] > 0)
        base_fail = r["before"]["failed"] > 0 or r["before"]["errors"] > 0
        if not after_ok:
            r["verdict"] = "AFTER_FAIL"  # fix 树上金测试不过且无豁免 → 环境或提取问题
        elif not base_fail:
            r["verdict"] = "PRE-PASS"
        elif r["before"]["errors"] > 0:
            r["verdict"] = "BROKEN_GOLD"  # 收集错误类失败需人工确认
        elif after_fail_nodes:
            r["verdict"] = "VALID*"  # 通过，但含已知环境噪音失败（见豁免清单）
        else:
            r["verdict"] = "VALID"
        return r
    finally:
        git(repo, "worktree", "remove", "--force", str(tmp / "head"))
        git(repo, "worktree", "remove", "--force", str(tmp / "base"))
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    chains = set(sys.argv[1:])
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    tasks = [t for t in MANIFEST if not chains or t["id"][:1] in chains]
    results = []
    counts: dict[str, int] = {}
    for t in tasks:
        r = check_task(t)
        results.append(r)
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        b, a = r.get("before"), r.get("after")
        bs = f"F{b['failed']}/E{b['errors']}/P{b['passed']}" if b else "n/a"
        as_ = f"F{a['failed']}/E{a['errors']}/P{a['passed']}" if a else "n/a"
        print(f"[{r['id']}] {r['verdict']:<12} {r['repo']:<12} {r['fix']} "
              f"before({bs}) after({as_}) "
              f"{len(r['gold_files'])} files — {r['desc'][:50]}", flush=True)
        (GOLD_DIR / "report.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n== 汇总: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
