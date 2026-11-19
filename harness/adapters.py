# -*- coding: utf-8 -*-
"""P3 agent 适配器：OpenCode 与 Aider 的统一调用契约。

契约（DESIGN_CN.md §三）：
    Adapter.run(workdir, prompt, model, timeout_s) -> AdapterResult
token 用量只采 adapter 官方输出（token_source=adapter）；解析不到时记
unavailable，绝估算、绝不造数。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
_IS_WIN = os.name == "nt"
AIDER_EXE = (WS / "experiments" / "venvs" / "aider" /
             ("Scripts/aider.exe" if _IS_WIN else "bin/aider"))


@dataclass
class AdapterResult:
    exit_code: int
    seconds: float
    transcript: str
    tokens_in: int | None = None      # None = adapter 未报告
    tokens_out: int | None = None
    token_source: str = "adapter"     # 或 "unavailable"
    extra: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2, ensure_ascii=False)


class BaseAdapter:
    name = "base"

    def run(self, workdir: Path, prompt: str, model: str, timeout_s: int = 1800,
            log_path: Path | None = None) -> AdapterResult:
        raise NotImplementedError


def _finalize(proc: subprocess.CompletedProcess | None, t0: float,
              exc: Exception | None = None) -> AdapterResult:
    if exc is not None:
        return AdapterResult(exit_code=-1, seconds=round(time.time() - t0, 1),
                             transcript=f"ADAPTER ERROR: {exc!r}",
                             token_source="unavailable")
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return AdapterResult(exit_code=proc.returncode, seconds=round(time.time() - t0, 1),
                         transcript=out, token_source="unavailable")


def _kill_tree(p: subprocess.Popen) -> None:
    """杀掉 agent 整棵进程树（Windows: taskkill /T；POSIX: 进程组 SIGKILL）。"""
    if _IS_WIN:
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                       capture_output=True)
    else:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def run_logged(cmd: list[str], cwd: Path, log_path: Path, timeout_s: int,
               completion_re: re.Pattern | None = None, idle_s: float = 120.0,
               poll_s: float = 2.0, input_text: str | None = None
               ) -> tuple[int, str, float, bool]:
    """运行 agent 并把 stdout+stderr 重定向到日志文件。

    返回 (exit_code, 日志文本, 耗时, early_reaped)。

    不用 capture_output 管道：Windows 上 agent 的孙进程（git 等）会继承并长期
    占住管道写端，subprocess.run 等 EOF 会无限挂起（实测）。文件重定向 +
    p.wait() 只等直接子进程，孙进程不再阻塞；超时用 taskkill /T 杀整棵进程树。

    completion_re + idle_s：挂死保护。agent 可能多轮自交互（实测 aider 每轮
    都打印 "Tokens: ... received"，中途还会问"加文件进对话吗"），行出现≠结束。
    收割条件 = 哨兵行出现过 **且** 日志静默 idle_s 秒（正常退出走不到这步，
    只有退出路径挂死才触发；留痕 early_reaped=True）。静默期取自日志 mtime，
    覆盖慢 API 轮次（v4-pro 思考可达分钟级，故默认 120s）。
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    deadline = t0 + timeout_s
    armed_since: float | None = None
    last_output = t0
    rc: int | None = None
    reaped = False
    with open(log_path, "wb") as f:
        p = subprocess.Popen(cmd, cwd=str(cwd), stdout=f,
                             stderr=subprocess.STDOUT,
                             stdin=subprocess.PIPE if input_text is not None
                             else subprocess.DEVNULL,
                             text=True, encoding="utf-8", errors="replace",
                             **({} if _IS_WIN else {"start_new_session": True}))
        if input_text is not None:
            try:
                p.stdin.write(input_text)
                p.stdin.close()
            except OSError:
                pass
        while True:
            try:
                rc = p.wait(timeout=poll_s)
                break
            except subprocess.TimeoutExpired:
                pass
            now = time.time()
            try:
                last_output = max(last_output, log_path.stat().st_mtime)
            except OSError:
                pass
            if completion_re is not None and armed_since is None:
                try:
                    text = log_path.read_text(encoding="utf-8", errors="replace")
                    if completion_re.search(text):
                        armed_since = now
                except OSError:
                    pass
            if armed_since is not None and now - max(last_output, armed_since) >= idle_s:
                _kill_tree(p)
                rc, reaped = 0, True
                f.write(f"\n[adapter] early reaped: sentinel seen + idle {idle_s}s"
                        .encode())
                break
            if now >= deadline:
                _kill_tree(p)
                rc = 124
                f.write(f"\nADAPTER TIMEOUT after {timeout_s}s".encode())
                break
    text = log_path.read_text(encoding="utf-8", errors="replace")
    return rc, text, round(time.time() - t0, 1), reaped


class AiderAdapter(BaseAdapter):
    """aider --message 单轮。--no-auto-commits：改动留在工作树由 runner 提交。"""

    name = "aider"

    def run(self, workdir: Path, prompt: str, model: str, timeout_s: int = 1800,
            log_path: Path | None = None) -> AdapterResult:
        cmd = [
            str(AIDER_EXE), "--model", model, "--message", prompt,
            "--yes-always", "--no-auto-commits", "--no-check-update",
            "--no-gitignore", "--no-pretty", "--no-fancy-input",
            "--no-show-model-warnings", "--chat-language", "English",
        ]
        lp = log_path or Path(tempfile.gettempdir()) / f"aa_{self.name}_{int(time.time())}.log"
        rc, text, secs, reaped = run_logged(
            cmd, workdir, lp, timeout_s,
            completion_re=re.compile(r"^Tokens: .+received", re.M),
            idle_s=120.0)
        r = AdapterResult(exit_code=rc, seconds=secs, transcript=text)
        r.extra["early_reaped"] = reaped
        # aider 用量行两种形态："Tokens: 784 sent, 1 received."（小值精确）
        # / "Tokens: 20k sent, 1.2k received."（大值 k 缩写，adapter 自身口径）
        m = re.findall(r"([\d.,]+)\s*([kKmM]?)\s*sent\D+?([\d.,]+)\s*([kKmM]?)\s*received",
                       text)

        def _n(num: str, suffix: str) -> int:
            v = float(num.replace(",", ""))
            return int(v * {"k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6}.get(suffix, 1))

        if m:
            r.tokens_in = sum(_n(a, s1) for a, s1, _, _ in m)
            r.tokens_out = sum(_n(b, s2) for _, _, b, s2 in m)
            r.token_source = "adapter"
            r.extra["tokens_exact"] = not any(s1 or s2 for _, s1, _, s2 in m)
        r.extra["cmd"] = cmd[:2] + ["<model>", "<prompt>"]
        return r


class OpenCodeAdapter(BaseAdapter):
    """opencode run 非交互模式（1.19.5）。npm 全局安装在 Windows 上是 .cmd shim，
    subprocess 裸名找不到——加载时解析绝对路径。"""

    name = "opencode"
    exe: str | None = None

    def __init__(self) -> None:
        exe = shutil.which("opencode") or shutil.which("opencode.cmd")
        if not exe:
            raise FileNotFoundError(
                "opencode not found on PATH; install with: npm install -g opencode-ai")
        OpenCodeAdapter.exe = exe

    # 无头模式遇 "ask" 权限自动拒绝（实测 external_directory 全线被拒，
    # agent 读不了文件→空转变假 REJECT）。**官方解法 = --auto**：自动批准
    # 未被显式 deny 的权限（run --help 原文 "dangerous!"，实验沙箱内可接受）。
    # 项目级全允许配置对 V1 的 external_directory 无效（实测三种形态均被拒），
    # 保留写入仅作声明。独立 git 仓库见 runner.py（V1 把 worktree 的项目根
    # 解析到主仓库）。
    ALLOW_CONFIG = {
        "$schema": "https://opencode.ai/config.json",
        "permission": {"edit": "allow", "bash": "allow", "webfetch": "allow",
                       "external_directory": {"*": "allow"}},
    }

    def run(self, workdir: Path, prompt: str, model: str, timeout_s: int = 1800,
            log_path: Path | None = None) -> AdapterResult:
        cfg = workdir / "opencode.json"
        cfg.write_text(json.dumps(self.ALLOW_CONFIG, indent=2), encoding="utf-8")
        exc_f = workdir / ".git" / "info" / "exclude"
        try:
            lines = exc_f.read_text(encoding="utf-8") if exc_f.exists() else ""
            if "opencode.json" not in lines:
                exc_f.parent.mkdir(parents=True, exist_ok=True)
                exc_f.write_text(lines + "\nopencode.json\n", encoding="utf-8")
        except OSError:
            pass
        # prompt 必须走 stdin：argv 传参会触发 opencode 服务端错误（实测）
        cmd = [OpenCodeAdapter.exe, "run", "--model", model, "--auto"]
        lp = log_path or Path(tempfile.gettempdir()) / f"aa_{self.name}_{int(time.time())}.log"
        t0_ms = int(time.time() * 1000) - 1000  # 1s 余量防时钟毛刺
        rc, text, secs, reaped = run_logged(cmd, workdir, lp, timeout_s,
                                            input_text=prompt)
        r = AdapterResult(exit_code=rc, seconds=secs, transcript=text)
        r.extra["early_reaped"] = reaped
        # headless run 不打印用量——从本地会话库取精确值（token_source=adapter）。
        # 注意：directory 字段记录的是工程根而非 worktree cwd，故按时间窗过滤
        # （runner 串行执行，一次只有一个活跃会话）。
        usage = self._latest_usage(t0_ms)
        if usage:
            r.tokens_in = usage["tokens_input"]
            r.tokens_out = usage["tokens_output"]
            r.token_source = "adapter"
            r.extra["usage_detail"] = usage
        r.extra["cmd"] = ["<opencode>", "run", "--model", "<model>", "<stdin:prompt>"]
        return r

    @staticmethod
    def _latest_usage(since_ms: int) -> dict | None:
        """从 opencode.db 取指定时刻之后最新会话的精确用量（USD cost 含内）。"""
        db = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
        if not db.exists():
            return None
        try:
            con = sqlite3.connect(str(db))
            row = con.execute(
                "SELECT directory, model, cost, tokens_input, tokens_output,"
                " tokens_reasoning, tokens_cache_read, tokens_cache_write, time_created"
                " FROM session WHERE time_created > ?"
                " ORDER BY time_created DESC LIMIT 1",
                (since_ms,),
            ).fetchone()
            con.close()
        except Exception:  # noqa: BLE001 — 用量通道失败不阻断主流程
            return None
        if not row:
            return None
        keys = ("directory", "model", "cost", "tokens_input", "tokens_output",
                "tokens_reasoning", "tokens_cache_read", "tokens_cache_write",
                "time_created")
        return dict(zip(keys, row))


ADAPTERS = {a.name: a for a in (AiderAdapter(), OpenCodeAdapter())}


def get_adapter(name: str) -> BaseAdapter:
    return ADAPTERS[name]
