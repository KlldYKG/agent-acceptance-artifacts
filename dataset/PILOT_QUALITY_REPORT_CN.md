# P2 步骤②：试点仓库质量校验报告（Python 首轮 + 放量轮）

> 生成：2026-11-16。工具：`dataset/quality_check.py`（浅克隆钉 commit → 独立 venv → `pip install -e .` → 全套 pytest 计时）。
> 环境：Windows 10，Python 3.13.14，pypi.org 直连（VPN 关闭态）。各仓库 HEAD SHA 为本轮实测钉点。

## 〇、放量轮新增（2026-11-16 晚）

| 仓库 | 钉点 commit | 可安装 | 全套耗时 | 结果 | 判定 |
|---|---|---|---|---|---|
| **pallets/click** | `e38188e9e205` | ✅（8 包） | **10.6s** | 2548 passed / 102 skipped | ✅ 标准 2/5/6 全过 → **链 D 载体** |

**放量轮新坑（重要，harness 设计项）**：click 测试依赖**不锁 pytest 版本**，HEAD 代码兼容 pytest 9，但 2026 年中的旧钉点代码在 pytest 9 下触发 `PytestRemovedIn10Warning` → `filterwarnings=error` → 收集错误。**解法：venv 钉 `pytest<9` 后 8 任务全 VALID**。含义：放量轮脚本化时，venv 测试依赖应按**钉点时代的兼容范围**安装（先试最新，收集错误再降级），这一"版本兼容降级"逻辑要进 harness。

## 一、试点首轮实测结果总览（2026-11-16 午）

| 仓库 | 钉点 commit | 可安装 | 全套耗时 | 结果 | 判定 |
|---|---|---|---|---|---|
| **encode/httpx** | `b5addb64f016` | ✅（extras: brotli,cli,http2,socks,zstd） | **21–24s** | 1414 passed / 3 failed / 1 skipped | ✅ 标准 2/5/6 全过 |
| **marshmallow-code/marshmallow** | `777ff66039fd` | ✅（+tzdata） | **1.6–2.6s** | 1192 passed / 0 failed | ✅ 标准 2/5/6 全过 |
| **andialbrecht/sqlparse** | `09dbe1eec31e` | ✅（零额外依赖） | **3.3–3.9s** | 537 passed / 2 xfailed / 1 xpassed | ✅ 标准 2/5/6 全过 |

三个试点仓库全部通过硬指标：**测试基建可跑（标准 2）、全套 <60s（标准 5，余量 2.5×–30×）、依赖轻可预装（标准 6，httpx 35 包 / marshmallow 11 包 / sqlparse 10 包）**。

## 二、httpx 3 个失败用例定性（均为环境噪音，非真实回归）

| 用例 | 原因 | 分类 |
|---|---|---|
| `test_main.py::test_download` | pytest 新版 `isolated_filesystem` DeprecationWarning 被 `filterwarnings=error` 放大 | 工具版本噪音（钉 pytest==8.4.1 可消除） |
| `test_multipart.py::test_multipart_encode_files_raises_exception_with_text_mode_file` | Windows 文本模式文件行为差异 | 平台噪音 |
| `test_timeouts.py::test_write_timeout[trio]` | Windows 计时精度下未触发 WriteTimeout | 平台计时敏感 |

→ 结论：失败率 3/1418 = 0.2%，全部可归因环境。**对实验的含义**：链任务复跑时须在报告层加"环境噪音豁免清单"（harness 设计项，记入 P2③）。

## 三、脚本踩坑记录（供放量轮复用）

1. **多装插件反而炸套件**：httpx 不用 pytest-asyncio（走 anyio 插件），装了最新版后其 deprecation warning 被 httpx 的 `filterwarnings=error` 升级为 INTERNALERROR。教训：**测试依赖必须对齐各仓库 requirements.txt，宁缺勿滥**（已在脚本注释中固化）。
2. **Windows 时区数据**：marshmallow 套件需要 `tzdata` 包（Linux 自带，Windows 没有）。放量轮所有含 `ZoneInfo` 的仓库都要加。
3. **extras 命名差异**：httpx extras 是 `brotli,cli,http2,socks,zstd`，通用猜测（dev/test）猜不中——脚本已支持按仓库指定 extras。

## 四、对 P2② 后续（issue 聚类）的输入

- 三仓库均可在本地 venv 快速复跑（最慢 httpx 24s），链设计时可放心做"每任务跑全套测试"的粒度。
- httpx 套件 1414 个用例规模大，金标准测试建议单独放 `dataset/gold/` 目录、只跑相关子集 + 最终全套确认。
- 下一步：从 issue 跟踪器导出候选 issue → 按"模块聚类 + 依赖关系"草拟 3 条链（httpx auth→redirect→transport / marshmallow fields→schema→error / sqlparse 解析→tokenize→format），每链 8–12 任务。
