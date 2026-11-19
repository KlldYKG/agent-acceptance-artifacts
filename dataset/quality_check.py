# -*- coding: utf-8 -*-
"""P2 步骤②：仓库质量校验脚本（筛选标准 2/5/6 硬指标实测）。

对每个试点仓库执行：
  1. 浅克隆（SSH 通道，记录钉住的 HEAD commit SHA）
  2. 创建独立 venv 并 `pip install -e .`（+ 尽力安装测试依赖组）
  3. 跑全套 pytest 并计时
判定：
  标准 2 测试基建：clone + 可安装 + pytest 套件可运行
  标准 5 测试速度：全套 <60s
  标准 6 依赖轻：安装成功且无重量级编译依赖（记录依赖数）

用法：
  python dataset/quality_check.py encode/httpx marshmallow-code/marshmallow \
      andialbrecht/sqlparse
输出：
  dataset/quality_report/<name>.json + 控制台摘要
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
REPOS_DIR = WS / "dataset" / "repos"
VENV_DIR = WS / "dataset" / "venvs"
REPORT_DIR = WS / "dataset" / "quality_report"
# 常见测试依赖组名，按序尽力安装（找不到的 extras pip 会报错，忽略即可）
TEST_EXTRA_CANDIDATES = ["dev", "test", "tests", "testing"]
# 个别仓库套件的已知运行前提（extras 覆盖不到时兜底）
# 注意：须对齐各仓库 requirements.txt / pyproject 的真实测试依赖，
# 宁缺勿滥——多装插件（如 pytest-asyncio）反而会炸掉把 warning 升级为 error 的套件。
REPO_EXTRAS: dict[str, str] = {"httpx": "brotli,cli,http2,socks,zstd", "black": "d"}
EXTRA_REQUIREMENTS: dict[str, list[str]] = {
    "httpx": ["pytest==8.4.1", "trio==0.31.0", "trustme==1.2.1", "uvicorn==0.35.0",
              "chardet==5.2.0", "cryptography"],
    "marshmallow": ["pytest", "pytest-mock", "simplejson", "tzdata"],
    "sqlparse": ["pytest"],
}


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None,
        timeout: int = 1800) -> tuple[int, str]:
    """执行命令，返回 (exit_code, 合并输出)。永不抛异常到外层。"""
    full_env = None
    if env:
        import os
        full_env = {**os.environ, **env}
    try:
        p = subprocess.run(
            cmd, cwd=str(cwd) if cwd else None, env=full_env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, shell=False,
        )
        out = (p.stdout or "") + "\n" + (p.stderr or "")
        return p.returncode, out
    except subprocess.TimeoutExpired:
        return 124, "TIMEOUT"
    except Exception as e:  # noqa: BLE001
        return 1, f"EXC: {e!r}"


def shorthttps_to_ssh(url: str) -> str:
    # 强制走 SSH（HTTPS 在关 VPN 环境被重置）
    return f"git@github.com:{url}.git"


def check_repo(slug: str) -> dict:
    name = slug.split("/")[-1]
    repo_path = REPOS_DIR / name
    venv_path = VENV_DIR / name
    report: dict = {"repo": slug, "name": name, "head": None, "ok_clone": False,
                    "ok_install": False, "ok_pytest": False,
                    "pytest_seconds": None, "passed": None, "failed": None,
                    "errors": None, "skipped": None, "notes": []}

    # ---- 1. clone ----
    t0 = time.time()
    if repo_path.exists():
        code, out = run(["git", "fetch", "--depth", "1", "origin"], cwd=repo_path, timeout=600)
        if code != 0:
            report["notes"].append(f"fetch failed, recloning: {out[-200:]}")
        else:
            code, out = run(["git", "reset", "--hard", "origin/HEAD"], cwd=repo_path, timeout=120)
    if not repo_path.exists() or report["notes"]:
        import shutil
        if repo_path.exists():
            shutil.rmtree(repo_path, ignore_errors=True)
        code, out = run(["git", "clone", "--depth", "1", shorthttps_to_ssh(slug),
                         str(repo_path)], timeout=900)
        if code != 0:
            report["notes"].append(f"clone failed: {out[-300:]}")
            return report
    report["ok_clone"] = True
    code, out = run(["git", "rev-parse", "HEAD"], cwd=repo_path)
    report["head"] = out.strip().splitlines()[0] if code == 0 else None
    report["clone_seconds"] = round(time.time() - t0, 1)

    # ---- 2. venv + install ----
    t0 = time.time()
    py = sys.executable
    if not venv_path.exists():
        code, out = run([py, "-m", "venv", str(venv_path)], timeout=600)
        if code != 0:
            report["notes"].append(f"venv failed: {out[-300:]}")
            return report
    vp = venv_path / "Scripts" / "python.exe"
    if not vp.exists():
        vp = venv_path / "bin" / "python"
    code, out = run([str(vp), "-m", "pip", "install", "--upgrade", "pip", "-q",
                     "-i", "https://pypi.org/simple"], timeout=600)
    install_cmds = [[str(vp), "-m", "pip", "install", "-q", "-e", "."]]
    if name in REPO_EXTRAS:
        install_cmds.append([str(vp), "-m", "pip", "install", "-q",
                             "-e", f".[{REPO_EXTRAS[name]}]"])
    for extra in TEST_EXTRA_CANDIDATES:
        install_cmds.append([str(vp), "-m", "pip", "install", "-q",
                             "-e", f".[{extra}]"])
    install_cmds.append([str(vp), "-m", "pip", "install", "-q",
                         *EXTRA_REQUIREMENTS.get(name, ["pytest"])])
    install_ok = False
    for ic in install_cmds:
        code, out = run(ic, cwd=repo_path, timeout=1200)
        if ic == install_cmds[0] and code != 0:
            report["notes"].append(f"install -e . failed: {out[-400:]}")
            return report
        if ic == install_cmds[0]:
            install_ok = True
    report["ok_install"] = install_ok
    report["install_seconds"] = round(time.time() - t0, 1)

    # 依赖计数（轻量判据：顶层已装包数）
    code, out = run([str(vp), "-m", "pip", "list", "--format=json"], timeout=120)
    if code == 0:
        try:
            report["installed_packages"] = len(json.loads(out))
        except json.JSONDecodeError:
            pass

    # ---- 3. full pytest with timing ----
    t0 = time.time()
    code, out = run([str(vp), "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
                    cwd=repo_path, timeout=3600)
    report["pytest_seconds"] = round(time.time() - t0, 1)
    report["ok_pytest"] = code in (0, 1)  # 1 = 有用例失败但套件可运行
    # 解析 "-q" 摘要行，如 "731 passed, 12 skipped in 45.20s"
    for line in out.splitlines():
        line = line.strip()
        if ("passed" in line or "no tests ran" in line) and " in " in line:
            summary = line.rsplit("=", 1)[-1].strip()
            report["pytest_summary"] = summary
            import re
            for key, pat in [("passed", r"(\d+) passed"), ("failed", r"(\d+) failed"),
                             ("errors", r"(\d+) error"), ("skipped", r"(\d+) skipped")]:
                m = re.search(pat, summary)
                if m:
                    report[key] = int(m.group(1))
            break
    if code not in (0, 1):
        report["notes"].append(f"pytest exit {code}: {out[-400:]}")
    return report


def main() -> int:
    slugs = sys.argv[1:] or ["encode/httpx", "marshmallow-code/marshmallow",
                             "andialbrecht/sqlparse"]
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    VENV_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for slug in slugs:
        print(f"\n===== {slug} =====", flush=True)
        r = check_repo(slug)
        results.append(r)
        (REPORT_DIR / f"{r['name']}.json").write_text(
            json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
        ok = lambda b: "✅" if b else "❌"  # noqa: E731
        print(f"  clone: {ok(r['ok_clone'])}  head={r['head']}")
        print(f"  install: {ok(r['ok_install'])}  ({r.get('install_seconds')}s, "
              f"{r.get('installed_packages', '?')} packages)")
        pt = r.get("pytest_seconds")
        speed = "✅(<60s)" if pt and pt < 60 else "❌(>=60s)"
        print(f"  pytest: {ok(r['ok_pytest'])}  {pt}s {speed}  "
              f"summary={r.get('pytest_summary', 'n/a')}")
        for n in r["notes"]:
            print(f"  note: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
