#!/usr/bin/env python3
"""V 轮：门控强度与可信度验证（本地零 API 成本）。

v1  PRE-PASS 误报率：50 个金测试任务物化成"正确实现+金测试"的 PR 喂门控，
    金测试应全判 VALID。任何非 VALID / 聚合非 EVIDENCE_OK = 误报。红线 <10%。
v2  确定性双跑：同一物化输入跑门控两次（含一次变异运行），判定须 100% 一致。
v3  对抗抽测（C4/sqlparse）：破坏性测试 / conftest 伪造 / 死循环，观察门控行为。
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

AA = Path("/root/aa")
sys.path.insert(0, str(AA / "dataset"))
import gold_check as gc  # noqa: E402

GATE_PY = AA / "experiments" / "venvs" / "gate" / "bin" / "python"
TMP = AA / "experiments" / "_vround"
OUTDIR = AA / "experiments" / "_vround_out"


def run(cmd, cwd, timeout=300, env=None):
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                          timeout=timeout, env=env)


def materialize(task):
    """物化 base(fix^) 与 head(fix+金测试) 独立仓库。返回 (wt, base, head, gold)。"""
    repo = gc.REPOS / task["repo"]
    fix = task["fix"]
    wt = TMP / ("m_" + task["id"])
    if wt.exists():
        shutil.rmtree(wt, ignore_errors=True)
    wt.mkdir(parents=True)
    with open(wt / "_.tar", "wb") as f:
        subprocess.run(["git", "-C", str(repo), "archive", fix + "^"],
                       stdout=f, check=True)
    subprocess.run(["tar", "-xf", "_.tar"], cwd=str(wt), check=True)
    (wt / "_.tar").unlink()

    ident = ["-c", "user.email=v@x", "-c", "user.name=v"]
    run(["git"] + ident + ["init", "-q"], wt)
    # 引导模块必须在 base 提交前写入，base/head 两棵树都有（门控双相都要导入）
    for rel, content in gc.REPO_BOOTSTRAP_FILES.get(task["repo"], {}).items():
        (wt / rel).write_text(content, encoding="utf-8")
    run(["git", "add", "-A"], wt)
    run(["git"] + ident + ["commit", "-qm", "base"], wt)
    base_sha = run(["git", "rev-parse", "HEAD"], wt).stdout.strip()

    diff = run(["git", "-C", str(repo), "diff", fix + "^", fix], repo).stdout
    p = wt / "_.patch"
    p.write_text(diff, encoding="utf-8")
    r = run(["git", "apply", "--whitespace=nowarn", "_.patch"], wt)
    p.unlink()
    if r.returncode != 0:
        return wt, base_sha, None, []
    authored = gc.AUTHORED_GOLD.get(task["id"])
    if authored:
        dst = wt / authored[0]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(gc.GOLD_DIR / "authored" / (task["id"] + ".py"), dst)
    run(["git", "add", "-A"], wt)
    run(["git"] + ident + ["commit", "-qm", "fix+gold"], wt)
    head_sha = run(["git", "rev-parse", "HEAD"], wt).stdout.strip()

    gold = [authored[0]] if authored else gc.changed_test_files(repo, fix)
    return wt, base_sha, head_sha, gold


def python_exe_for(repo_name):
    """src 布局仓库的导入修正：包装器按自身 cwd 解析 PYTHONPATH。

    门控对 base/head 两相共用一个 python_exe 与 env；外层固定 PYTHONPATH 会把
    head 代码泄漏进 base 运行（实测 D3 全 PRE-PASS 假象）。包装器让每次调用
    按当前 cwd（=门控给该相的树）解析，base 相导入 base 代码。
    """
    venv_py = gc.VENV(repo_name)
    if not gc.SRC_SUBDIR.get(repo_name):
        return venv_py
    wrapper = TMP / f"pywrap_{repo_name}.sh"
    TMP.mkdir(exist_ok=True)
    src = gc.SRC_SUBDIR[repo_name][0]
    wrapper.write_text(
        "#!/bin/bash\n"
        f'export PYTHONPATH="$PWD:$PWD/{src}"\n'
        f'exec "{venv_py}" "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)
    return wrapper


def run_gate(wt, base, head, repo_name, out, mutation_budget=None, timeout=1500):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)  # 防外层树泄漏进 base 相
    cmd = [str(GATE_PY), "-m", "agent_acceptance.cli", "run",
           "--repo", str(wt), "--base", base, "--head", head,
           "--python", str(python_exe_for(repo_name)), "--out", str(out)]
    if mutation_budget:
        cmd += ["--mutation-budget", str(mutation_budget)]
    # 门控自带 --phase-timeout=900（V3-C 后加的），外层再兜底 1500s。
    # Popen+进程组：超时必须击杀整组，否则 pytest 孙进程泄漏（实测孤儿 1h+）。
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, 9)
        except ProcessLookupError:
            pass
        proc.wait(timeout=60)
        return {"verdict": "TIMEOUT", "strength": None, "tests": []}
    ev = out / "evidence.json"
    if not ev.exists():
        return None
    return json.loads(ev.read_text(encoding="utf-8"))


def v1(only=None, tag="v1"):
    TMP.mkdir(exist_ok=True)
    OUTDIR.mkdir(exist_ok=True)
    tasks = [t for t in gc.MANIFEST if not only or t["id"] in only]
    results = []
    for i, t in enumerate(tasks):
        t0 = time.time()
        wt, base, head, gold = materialize(t)
        if head is None:
            results.append({"id": t["id"], "status": "materialize_fail"})
            print(f"[{i+1}/{len(tasks)}] {t['id']} materialize_fail", flush=True)
            continue
        out = OUTDIR / (tag + "_" + t["id"])
        ev = run_gate(wt, base, head, t["repo"], out)
        rec = {"id": t["id"], "repo": t["repo"], "gold": gold}
        if ev is None:
            rec.update(status="no_evidence_json", fp=True)
        else:
            rows = ev.get("tests", [])

            def _matches(r):
                tid = str(r.get("test", ""))
                return any(g[:-3].replace("/", ".") in tid for g in gold)

            grow = [r for r in rows if _matches(r)]
            rec.update(
                status="ok",
                gate_verdict=ev.get("verdict"), strength=ev.get("strength"),
                gold_rows=[{k: r.get(k) for k in ("test", "verdict")}
                           for r in grow],
                n_gold_valid=sum(1 for r in grow if r.get("verdict") == "VALID"),
                # gold 是文件级清单，同文件存量测试判 PRE-PASS 属正常；
                # 误报 = 门控整体拒绝，或金测试行里连一个 VALID 都没有。
                fp=(ev.get("verdict") != "EVIDENCE_OK" or
                    not any(r.get("verdict") == "VALID" for r in grow)),
            )
        shutil.rmtree(wt, ignore_errors=True)
        results.append(rec)
        print(f"[{i+1}/{len(tasks)}] {t['id']} {rec.get('status')} "
              f"gate={rec.get('gate_verdict')} str={rec.get('strength')} "
              f"fp={rec.get('fp')} ({time.time()-t0:.0f}s)", flush=True)
        (OUTDIR / f"{tag}_results.json").write_text(
            json.dumps(results, indent=1), encoding="utf-8")
    ok = [r for r in results if r.get("status") == "ok"]
    fps = [r for r in ok if r.get("fp")]
    print(f"\n== V1 汇总: 有效 {len(ok)}/{len(results)} | 误报 {len(fps)} "
          f"| 误报率 {len(fps)/max(len(ok),1)*100:.0f}%（红线 <10%）", flush=True)
    for r in fps:
        print("  FP:", r["id"], r.get("gate_verdict"), r.get("gold_rows"))


def v2():
    ids = ["A1", "B2", "C4", "D3", "E2"]
    TMP.mkdir(exist_ok=True)
    OUTDIR.mkdir(exist_ok=True)
    print("== V2 确定性双跑（判定一致性 + 1 次变异双跑）", flush=True)
    consist = []
    for tid in ids:
        t = next(x for x in gc.MANIFEST if x["id"] == tid)
        wt, base, head, gold = materialize(t)
        if head is None:
            print(tid, "materialize_fail", flush=True)
            continue
        runs = []
        for k in (1, 2):
            ev = run_gate(wt, base, head, t["repo"], OUTDIR / f"v2_{tid}_{k}")
            runs.append(ev and (ev.get("verdict"), ev.get("strength"),
                                tuple(sorted((r.get("key"), r.get("verdict"))
                                             for r in ev.get("tests", [])))))
        same = runs[0] == runs[1]
        consist.append(same)
        print(f"{tid}: {'一致' if same else '不一致!!'} | "
              f"{runs[0][0] if runs[0] else None} vs {runs[1][0] if runs[1] else None}",
              flush=True)
        shutil.rmtree(wt, ignore_errors=True)
    # 变异双跑（C4，预算 120s）
    t = next(x for x in gc.MANIFEST if x["id"] == "C4")
    wt, base, head, gold = materialize(t)
    mruns = []
    for k in (1, 2):
        ev = run_gate(wt, base, head, t["repo"], OUTDIR / f"v2_mutC4_{k}",
                      mutation_budget=120, timeout=900)
        mruns.append(ev and (ev.get("verdict"), ev.get("strength"),
                             json.dumps(ev.get("mutation", {}), sort_keys=True)))
    msame = mruns[0] == mruns[1]
    print(f"C4+mutation: {'一致' if msame else '不一致!!'} | {mruns[0]} | {mruns[1]}",
          flush=True)
    shutil.rmtree(wt, ignore_errors=True)
    print(f"\n== V2 汇总: 普通双跑 {sum(consist)}/{len(consist)} 一致 | "
          f"变异双跑 {'一致' if msame else '不一致'}", flush=True)


def v3():
    """C4 三类对抗样本。"""
    TMP.mkdir(exist_ok=True)
    OUTDIR.mkdir(exist_ok=True)
    t = next(x for x in gc.MANIFEST if x["id"] == "C4")
    findings = []

    def prep(attack_files: dict[str, str]):
        wt, base, head, gold = materialize(t)
        ident = ["-c", "user.email=v@x", "-c", "user.name=v"]
        for rel, content in attack_files.items():
            p = wt / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        run(["git", "add", "-A"], wt)
        run(["git"] + ident + ["commit", "-qm", "attack"], wt)
        return wt, base, run(["git", "rev-parse", "HEAD"], wt).stdout.strip()

    # A) 破坏性测试：运行时删除源文件
    wt, base, head = prep({"tests/test_zz_destructive.py": (
        "import pathlib\n"
        "def test_zz_destructive():\n"
        "    p = pathlib.Path('sqlparse/engine.py')\n"
        "    p.unlink()\n"
        "    assert True\n")})
    ev = run_gate(wt, base, head, t["repo"], OUTDIR / "v3_A", timeout=900)
    findings.append(("A 破坏性测试", {
        "verdict": ev and ev.get("verdict"), "strength": ev and ev.get("strength"),
        "rows": ev and len(ev.get("tests", [])),
        "tree_intact": (wt / "sqlparse" / "engine.py").exists(),
    }))
    shutil.rmtree(wt, ignore_errors=True)

    # B) conftest 伪造：把所有失败改成通过
    conftest = (
        "import pytest\n"
        "@pytest.hookimpl(hookwrapper=True)\n"
        "def pytest_runtest_makereport(item, call):\n"
        "    outcome = yield\n"
        "    rep = outcome.get_result()\n"
        "    if rep.when == 'call' and rep.failed:\n"
        "        rep.outcome = 'passed'\n")
    wt, base, head = prep({"tests/conftest_attack.py": conftest})
    ev = run_gate(wt, base, head, t["repo"], OUTDIR / "v3_B", timeout=900)
    findings.append(("B conftest 伪造", {
        "verdict": ev and ev.get("verdict"), "strength": ev and ev.get("strength"),
        "note": "conftest_attack.py 非 conftest.py 是否被自动加载？若未加载则门控天然免疫此路径",
        "rows": ev and [(r.get("key"), r.get("verdict")) for r in ev.get("tests", [])][:5],
    }))
    shutil.rmtree(wt, ignore_errors=True)
    # B2 真 conftest.py（会被自动加载）
    wt, base, head = prep({"tests/conftest.py": conftest})
    ev = run_gate(wt, base, head, t["repo"], OUTDIR / "v3_B2", timeout=900)
    findings.append(("B2 真 conftest.py", {
        "verdict": ev and ev.get("verdict"), "strength": ev and ev.get("strength"),
        "rows": ev and [(r.get("key"), r.get("verdict")) for r in ev.get("tests", [])][:5],
    }))
    shutil.rmtree(wt, ignore_errors=True)

    # C) 资源耗尽：死循环测试
    wt, base, head = prep({"tests/test_zz_hang.py": (
        "import time\n"
        "def test_zz_hang():\n"
        "    while True:\n"
        "        time.sleep(1)\n")})
    t0 = time.time()
    # 外层 2000s 兜底：门控内部 --phase-timeout=900 应先触发（base/pr 两相
    # 各挂 900s），验证工具自身超时修复而非外层击杀。
    ev = run_gate(wt, base, head, t["repo"], OUTDIR / "v3_C", timeout=2000)
    findings.append(("C 死循环测试", {
        "verdict": ev and ev.get("verdict"),
        "elapsed": round(time.time() - t0),
        "graceful": ev is not None,
    }))
    shutil.rmtree(wt, ignore_errors=True)

    print("== V3 对抗抽测结果", flush=True)
    for name, f in findings:
        print(f"  {name}: {json.dumps(f, ensure_ascii=False)}", flush=True)
    (OUTDIR / "v3_results.json").write_text(
        json.dumps(findings, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sub = sys.argv[1] if len(sys.argv) > 1 else "v1"
    if sub == "v1":
        v1(sys.argv[2].split(",") if len(sys.argv) > 2 else None)
    elif sub == "v2":
        v2()
    elif sub == "v3":
        v3()
