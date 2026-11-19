# P2 Harness 使用指南（dataset 管线）

> 2026-11-16 定稿。数据集 50 任务 / 5 链的构建与复验管线，全部单命令可跑。
> 读者：未来接手数据集扩展（放量轮、中文仓库轮）或 P3 harness 驱动的执行者。

## 一、管线总览（三个脚本，顺序固定）

```
quality_check.py  →  gold_check.py  →  run_chain.py
   仓库准入            任务双向验证        单命令复跑入口
```

| 脚本 | 作用 | 调用方式 |
|---|---|---|
| `quality_check.py` | 新仓库准入：浅克隆钉 commit → 独立 venv → `pip install -e .` → 全套 pytest 计时。验证筛选标准 2（测试可跑）/5（<60s）/6（依赖可装） | `python dataset/quality_check.py owner/repo [owner2/repo2 ...]` |
| `gold_check.py` | 单任务/单链金测试双向有效性验证（worktree fix^ + 覆盖 fix 版测试 → 应失败；fix 树 → 应通过） | `python dataset/gold_check.py [A\|B\|C\|D\|E]`（无参=全量） |
| `run_chain.py` | 复跑入口：全量或指定链，输出汇总表 | `python dataset/run_chain.py [A\|B\|C\|D\|E]` |

**当前清单：5 链 50 任务，全量复验 5.7 分钟，50/50 可用（49 VALID + 1 VALID\*）。**
最终任务清单以 `gold_check.py` 顶部 `MANIFEST` 为准（含每任务 fix commit 哈希与描述）。

## 二、方法学（为什么这样构建）

- **每个任务钉在上游真实修复提交（fix commit）的父提交**：此时 bug 存在、金测试失败；agent 的任务 = 修复 bug 让测试通过。
- **金测试 = fix 自带的回归测试**（`git diff fix^ fix -- tests` 自动提取），仅 2 个任务手写（`dataset/gold/authored/`，各 ≤10 行）。
- **链 = 同一模块内按时间排序的 fix 序列**：依赖关系天然真实，无需人工编造。
- **issue→fix 映射两策略**：sqlparse 直接在提交信息里写 `fixes #N`；marshmallow/httpx 需 PR 号反查（`git log --grep=<PR号>`）。
- **B1 类特殊场景**：修复与测试分属兄弟提交 → 用合并提交 + first-parent diff 提取（manifest 已定格为 `39e7c833`）。

## 三、gold_check.py 内置的四类机制（扩展新仓库前必读）

1. **环境噪音豁免（`KNOWN_NOISE_NODES`）**：已知平台噪音失败节点（当前 3 个，全是 Windows 特有）命中时 `AFTER_FAIL` 自动升级 `VALID*`。Linux CI 跑同一清单**无需**豁免（跨平台矩阵按平台注入）。
2. **自写金测试（`AUTHORED_GOLD` + `dataset/gold/authored/`）**：上游 fix 不带测试时，手写测试放 authored/ 目录，脚本自动复制到两棵树。
3. **数据驱动测试转换（`DATA_CASE_DIRS`）**：black 类仓库 fix 只加数据用例文件（`tests/data/cases/*.py`），pytest 目标须转成 `tests/test_format.py::test_simple_format[<用例名>]` 精确节点 ID——直接把数据文件喂给 pytest 必报收集错误。
4. **生成模块注入（`REPO_BOOTSTRAP_FILES`）**：black 的 `_black_version.py` 由打包钩子生成、源码树没有 → 验证前自动注入树根。

## 四、环境坑清单（全部踩过并已固化）

| 坑 | 后果 | 规则 |
|---|---|---|
| venv 里残留 `pip install -e .` 的可编辑安装 | 元路径finder 穿透 PYTHONPATH，钉 fix^ 的树跑成 HEAD 代码 → fail-before 假变 pass | 质量校验后**必须卸载**被测包（gold_check 前置检查） |
| 多装测试插件（如给 httpx 装 pytest-asyncio） | 仓库锁定的 filterwarnings=error 把弃用警告升级成 INTERNALERROR | 测试依赖**宁缺勿滥**，只装仓库自己声明锁定的 |
| 测试依赖不锁版本（click 不锁 pytest） | 旧钉点代码在 pytest 9 下收集错误 | venv 按**钉点时代**降级（click 钉 `pytest<9`）；harness 需内建此逻辑 |
| Windows 缺 tzdata | marshmallow 测试崩 | Windows venv 必装 `tzdata` |
| `--python` 相对路径 | worktree 内失效，pytest 静默失败判 ERROR 零诊断 | **已在工具 v1.0.0+ 修复**（cd38f84：绝对路径解析 + PytestRunnerError 带诊断） |
| GBK Windows 上 `write_text` 无 encoding | 非 ASCII 崩溃 | 所有脚本钉死 `encoding="utf-8"` |

## 五、放量新仓库 SOP（照做即可）

1. `quality_check.py <owner/repo>`——全套 <60s 且依赖可装才准入（httpie 因 240s 被淘汰）；
2. `git fetch --unshallow` 后挖 fix 史：`git log --grep="fix" -i --since=<钉点前1年>`，挑 **8–12 个带测试的 fix**，按模块聚类+时间排序成链；
3. 在 `gold_check.py` 登记：`SRC_SUBDIR`（源码布局）、`VENV` extras/requirements、新链 MANIFEST 条目；特殊机制按第三节四类登记；
4. 卸载 venv 里的可编辑安装 → `run_chain.py <新链>` → 全 VALID 即接入；
5. 更新本文档清单表与 `PILOT_QUALITY_REPORT_CN.md`。

## 六、验收对照（P2 提示词口径）

| 验收线 | 现状 |
|---|---|
| 30–50 条任务链 | ✅ 50 条（压上限） |
| 每链 8–12 依赖任务 | ✅（A8 / B11 / C10 / D11 / E10） |
| 金标准测试 + 质量校验脚本 | ✅（50/50 双向有效，仅 2 个手写金测试） |
| 单命令复跑任一链 | ✅ `python dataset/run_chain.py [链ID]` |
| 3–5 链兼作项目回归床 | ✅ 恰 5 链，全量 5.7min |
