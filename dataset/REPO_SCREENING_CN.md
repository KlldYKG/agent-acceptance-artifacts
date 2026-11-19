# P2 步骤①：仓库筛选（Python 试点轮）

> 生成：2026-11-16。裁决前提：OpenCode + Aider；先 Python（TS 与中文仓库在放量轮补入）。
> 目标：从候选池确定 15–20 个仓库（P2 终态），本轮先核实 12 个 + 淘汰名单 + 试点推荐。
> 数据来源：GitHub API（连接器核验于 2026-11-16）+ 领域常识（标注"待脚本验证"项由 P2② 的质量校验脚本实测）。

## 一、硬性筛选标准（提示词口径 + 实验可行性细化）

| # | 标准 | 可操作判据 |
|---|---|---|
| 1 | 许可证允许 | MIT / Apache-2.0 / BSD（数据集再分发需附带原始许可；排除 GPL 系） |
| 2 | 测试基建完善 | pytest 套件存在、CI 配置在库、可 `pip install -e .` 后直接跑 |
| 3 | issue 历史清晰 | 有真实 feature/bug issue 流（开放或已关闭皆可——链任务钉在固定 commit 上，用历史 issue 即可）；有标签或可按模块聚类 |
| 4 | 链友好（8–12 个有依赖关系的任务/链） | 单一模块内可提取多个小粒度、有先后依赖的 issue（如 httpx 的 auth→redirect→cookie 层级） |
| 5 | 测试套件快 | **关键工程约束**：每条链要被复跑 ≥3 次 × 多实验臂，全套测试须 <60s（排除动辄 10 分钟的科学计算套件） |
| 6 | 依赖轻、可沙箱安装 | 依赖树浅，容器内 `--network none` 前可预装完毕 |
| 7 | 中等规模 | 3k–60k stars、非 archived、近 3 个月有 push（太冷门缺 issue 史，太大审查面广） |

## 二、已核实候选（连接器实查，2026-11-16）

| 仓库 | 许可证 | stars | 开放 issue | 最近 push | 链友好性初判 |
|---|---|---|---|---|---|
| **encode/httpx** | BSD-3 | 15.8k | 136 | 2026-10-02 | ★★★ auth/redirect/transport 分层清晰，小 issue 密集 |
| **pallets/click** | BSD-3 | 17.8k | 84 | 2026-11-15 | ★★★ 参数类型/装饰器/终端模块 issue 粒度小 |
| **Textualize/rich** | MIT | 57.8k | 402 | 2026-11-16 | ★★☆ 渲染原语多但模块耦合度待查；issue 量大 |
| **marshmallow-code/marshmallow** | MIT | 7.2k | 173 | 2026-11-16 | ★★★ fields/schema/validation 层级天然成链 |
| **andialbrecht/sqlparse** | BSD-3 | 4.0k | 324 | 2026-11-15 | ★★★ 解析/格式化 issue 粒度小、测试快 |
| **pallets/werkzeug** | BSD-3 | 6.9k | 6* | 2026-11-09 | ★★☆ 开放 issue 极少（维护者关门快），但历史已关闭 issue 庞大——链用历史 issue 即可，保留 B 档 |

*开放 issue 少不是硬伤：链任务钉在历史 commit + 历史 issue 上，不依赖当前积压。

## 三、知识库候选（许可证/形态确定，量化指标待脚本验证）

| 仓库 | 许可证 | 备注 |
|---|---|---|
| psf/requests | Apache-2.0 | 经典；但近年 issue 流偏慢，链友好性存疑 |
| httpie/httpie | BSD-3 | CLI 形态，测试友好；issue 粒度待查 |
| psf/black | MIT | 格式化器，输入输出极确定（金测试好写）；issue 偏大粒度 |
| PyCQA/flake8 | MIT | 插件生态广；核心模块 issue 待聚类 |
| pytest-dev/pytest | MIT | 测试基建最完善；"用 pytest 测 pytest"有递归趣味但无冲突 |
| jazzband/tablib | MPL-2.0 | 弱 copyleft，数据集再分发可用；小仓库 issue 量是短板 |
| burnash/gspread | MIT | 小而清晰；issue 粒度待查 |

## 四、淘汰名单（含理由，防复审再捡）

| 仓库 | 淘汰理由 |
|---|---|
| tiangolo/typer | 主仓库 issue 管理长期积压、生态仓库 typer-cli 已 archived；上游活跃度模式不利金测试长期有效 |
| encode/starlette | 连接器检索异常（待人工复查）；与 httpx 生态重叠，试点轮不急 |
| scikit-learn / pandas / numpy | 测试套件分钟级～小时级，违反标准 5（链复跑成本爆炸） |
| pypa/pip-tools | 利益冲突（已拒绝外联，避免"落选者报复"观感）；且属"已核实迁移"的敏感期项目 |
| JumpServer 等中文大项目 | AGPL/GPL 许可证违反标准 1 |
| sqlmap | GPL-2.0，排除 |

## 五、中文社区仓库（放量轮补入，RESEARCH_PLAN 要求 2–3 个）

- 判据：许可证宽松 + GitHub 主场（harness 需要 git/CI 基建，Gitee 镜像不稳）+ pytest 套件 + issue 可聚类。
- 候选方向（待核验）：NoneBot2（MIT，聊天机器人框架，issue 流活跃）、sqlfluff（国际但中文用户多）不满足"中文社区"定义、其他需专轮调研——**留到放量轮**，试点轮不阻塞。

## 六、试点推荐（3–5 条链的载体）

| 试点 | 仓库 | 链主题方向 | 理由 |
|---|---|---|---|
| 1 | **httpx** | 认证→重定向→传输层的 8–10 个依赖 bug 修复 | 分层结构天然给依赖关系；测试快（实测项） |
| 2 | **marshmallow** | fields→schema→error handling 依赖链 | 数据校验域与 httpx 域异质，避免单域偏置 |
| 3 | **sqlparse** | 解析→tokenize→format 依赖链 | 第三域：解析器；324 开放 issue 选材余地大 |
| 4（备） | click | 参数处理→命令分组→异常链 | 三条主链不够时补位 |

试点达标后（可复跑验收过），再从第三节候选补到 15–20 个并开启 TS/中文轮。

## 七、下一步（P2 步骤②入口）

1. 对试点 3 仓库执行**质量校验脚本**：克隆钉 commit → `pip install -e .` → 跑全套测试计时 → 判定标准 2/5/6 硬指标；
2. 从 issue 跟踪器导出候选 issue 清单，按"模块聚类 + 依赖关系"草拟 3 条链（每链 8–12 任务）；
3. 每任务预埋金标准测试，校验脚本须证明：依赖可执行 + **金测试自身双向有效**（复用我们 agent-acceptance 的 `run` 后端！——工具第一次吃自己的狗粮）。
