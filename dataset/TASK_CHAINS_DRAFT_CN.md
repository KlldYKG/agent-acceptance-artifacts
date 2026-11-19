# P2 步骤②：任务链草案（3 条试点链）

> **修订（2026-11-16 晚，验证后定稿）**：链 A 的 A3（3f76571 纯重构无区分测试）替换为 `7c0cda1` InvalidURL 错误消息；A8（8ecb86f 纯测试提交）替换为 `6d852d3` send() 超时修复。链 B 剔除 B4（3bc191ab typing-only 无运行时行为，#3005 浅合并 bug 上游未修——该提交恰由 Claude 协作完成，留作叙事素材）。链 C 的 C4 金测试自写（`dataset/gold/authored/C4.py`）。**本文表为草案存档，最终清单以 `gold_check.py` 的 MANIFEST 为准**（编号已按时间线重排：链 A 现在 A1=99cba6a → A8=9fd6f0c；链 B 现在 B1=8dc078e2(经合并提交 39e7c833 提取) → B10=5761beab）。

> 生成：2026-11-16。前提：试点三仓库质量校验全过（见 `PILOT_QUALITY_REPORT_CN.md`）。
> 数据来源：GitHub issue 跟踪器导出 + 本地全量 git 历史核对 fix commit（逐条人工映射，非猜测）。

## 一、方法学：链任务如何"钉"在真实历史上

**核心机制（对齐 SWE-bench 传统，避免重复上游已修复的问题）**：

1. 每个任务 = 一个**有可识别 fix commit 的真实 issue**；
2. 仓库状态钉在 **fix commit 的父提交（fix^）**——此时 bug 存在、金测试应当失败；
3. **金标准测试 = fix commit 引入的回归测试**（上游已验证过的正确行为定义）；
4. agent 的任务 = 在 fix^ 状态下，按 issue 描述实现修复，使金测试由失败变通过；
5. **链 = 同一模块内、按提交时间排序的 fix 序列**：任务 N 的起点状态自动包含前 N-1 个修复（自然的依赖关系，无需人工造依赖）。

**issue → fix commit 的两种映射策略**（放量轮脚本化）：
- sqlparse 式：commit message 直接写 `fixes #N` / `issue N`（如 `da67ac1 (fixes #827)`）；
- marshmallow/httpx 式：commit message 写 PR 号 `(#NNNN)`，需经 PR 页面反查关联 issue。

**选链约束**：
- fix 序列须落在**近 12–24 个月**内（sqlparse API 极稳可放宽到 2024-03 起），防止钉点状态与当前测试基建脱节；
- 每任务粒度：单文件~单模块小修复，金测试可独立运行（秒级）；
- 同日多 fix（marshmallow 2026-03-25/26 爆发）按提交线性顺序展开，跨模块交错不影响——每任务只要求自己模块的行为。

## 二、链 A：httpx —— 「认证 → URL 构造 → 内容编码」（8 任务）

钉仓：`dataset/repos/httpx` @ `b5addb64f016`（质量校验已过，全套 21s）

| # | fix commit | 日期 | issue/PR 源 | 模块 | 任务摘要 | 依赖前驱 |
|---|---|---|---|---|---|---|
| A1 | `99cba6a` | 2024-01-10 | DigestAuth RFC 2069（#3306 同域） | `_auth.py` | 修复 RFC 2069 模式摘要认证 | — |
| A2 | `49d74a2` | 2024-09-26 | #3313 | `_models.py` | header 值为 None 时给出明确错误 | — |
| A3 | `3f76571` | 2024-10-25 | PR #3364 | `_urls.py` | URL 实例化精简重构（行为保持） | A2 |
| A4 | `d293374` | 2024-10-28 | PR #3371 | `_urlparse.py` | 按 WHATWG 修订百分号转义集 | A3 |
| A5 | `ba2e512` | 2024-10-28 | PR #3373（关联 #3413 '+' 编码） | `_urlparse.py` | form 空格的 `+` 行为 | A4 |
| A6 | `5dda2aa` | 2024-10-28 | PR #3376 | `_urlparse.py` | urlescape 默认 safe 字符集 | A5 |
| A7 | `9fd6f0c` | 2024-10-28 | #3363 | `_content.py` | JSON 序列化紧凑输出（可配置空格） | — |
| A8 | `8ecb86f` | 2024-12-04 | PR #3440（关联 #3483/#3550 params 语义） | `_urls.py` | params 合并行为测试锁定 | A6 |

链叙事：认证层 → 错误信息 → URL 解析/编码逐层收紧 → 序列化 → params 语义定型。

## 三、链 B：marshmallow —— 「fields → validators → schema」（11 任务）

钉仓：`dataset/repos/marshmallow` @ `777ff66039fd`（质量校验已过，全套 1.6s）

| # | fix commit | 日期 | issue/PR 源 | 模块 | 任务摘要 | 依赖前驱 |
|---|---|---|---|---|---|---|
| B1 | `8dc078e2` | 2026-01-10 | #2891 | `validate.py` | 大写 `file:` URL 误报 ValidationError | — |
| B2 | `19ca8dce` | 2026-02-04 | #2868 / PR #2894 | `fields.py` | Constant 字段接受 None 值 | — |
| B3 | `070dde08` | 2026-03-25 | #2900/#2915 / PR #2901 | `fields.py` | Constant(required=True) 不再抛 ValueError | **B2** |
| B4 | `3bc191ab` | 2026-03-25 | #3005 / PR #2907 | `fields.py` | error_messages 支持嵌套 dict/list 值 | B2 |
| B5 | `65374df0` | 2026-03-25 | #2869 / PR #2909 | `validate.py` | OneOf.options() 消除标签错位的幻影条目 | B1 |
| B6 | `252090c7` | 2026-03-26 | PR #2903 | `fields.py` | Nested partial 前缀用 attr_name 而非 data_key | B4 |
| B7 | `024b5d09` | 2026-03-26 | PR #2902（关联 #2985） | `fields.py` | Enum 按名查找只返回真实成员 | B6 |
| B8 | `72ac4a04` | 2026-03-26 | PR #2904 | `fields.py` | from_timestamp_ms 拒绝布尔值 | — |
| B9 | `f07eadc8` | 2026-04-02 | #2936 / PR #2937 | `validate.py` | Email 校验器支持 IDN 域名 | B1/B5 |
| B10 | `902f99c4` | 2026-08-08 | PR #3016 | `validate.py` | URL 校验器接受空路径后带 fragment | **B9** |
| B11 | `5761beab` | 2026-10-18 | （Pluck 系列） | `fields.py` | Pluck 空 data_key 处理 | B7 |

链叙事：fields 基类语义（Constant 系两次迭代 = 天然依赖）→ 校验器（Email/URL 同域递进）→ 嵌套结构。11 任务超出 8–12 口径下限、贴近上限。

## 四、链 C：sqlparse —— 「关键词识别 → 语句切分 → 格式化」（10 任务）

钉仓：`dataset/repos/sqlparse` @ `09dbe1eec31e`（质量校验已过，全套 3.3s）

| # | fix commit | 日期 | issue 源 | 模块 | 任务摘要 | 依赖前驱 |
|---|---|---|---|---|---|---|
| C1 | `6b05583` | 2024-03-16 | #682 | `keywords.py` | `->` 识别为单一操作符 | — |
| C2 | `791e25d` | 2024-07-15 | #784 | `engine/filter.py` | BEGIN 块内多 CASE 子句不再被切开 | C1 |
| C3 | `0c4902f` | 2024-07-15 | #782 | `formatter.py` | CTE 查询格式化幂等（多余空格） | — |
| C4 | `e48000a` | 2024-07-19 | #785 | `keywords.py` | EXTENSION 列入关键词 | C1 |
| C5 | `73c8ba3` | 2025-03-14 | #801 | `formatter.py` | strip_comments 清除"仅注释"语句 | C3 |
| C6 | `1a3bfbd` | 2025-11-28 | #809 | `engine/filter.py` | BEGIN…END 内分号不再切分语句 | **C2** |
| C7 | `5ca50a2` | 2025-11-29 | #826 | `engine/filter.py` | BEGIN TRANSACTION 切分回归修复 | C6 |
| C8 | `da67ac1` | 2025-12-08 | #827 | `engine/grouping.py` | DoS 防护超限抛 SQLParseError 而非静默 None | C6 |
| C9 | `8f978ca` | 2026-05-21 | #845 | `engine/filter.py` | 切分器栈式重构：FOR/IF/WHILE 块 | C6/C7 |
| C10 | `ac3b9e0` | 2026-06-16 | #752 | `keywords.py` | MATERIALIZED 列入关键词 | C4 |

链叙事：token/关键词层 → 切分器演进线（C2→C6→C7→C9 依赖最强，真实"同一子系统多次迭代"）→ 格式化。issue 引用 `fixes #N` 格式，映射零歧义。

## 五、三链覆盖核对（对照提示词口径）

| 口径要求 | 现状 |
|---|---|
| 8–12 依赖任务/链 | A=8 ✅ B=11 ✅ C=10 ✅ |
| 任务粒度小 | 全部单模块小修复 ✅ |
| 依赖关系真实 | 全部来自"同模块时间先后 + 行为叠加"，零人工造依赖 ✅ |
| 三域异质 | HTTP 客户端 / 数据校验 / SQL 解析器 ✅ |
| 每任务可金测 | fix commit 自带回归测试（待提取）⏳ |

## 六、下一步（P2③ 入口）

1. **金测试提取**：对每个 fix commit 提取其 diff 中的新增测试（`git show <fix> -- tests/`），落到 `dataset/gold/<chain>/<task>/`；
2. **双向有效性狗粮验证**：用 `agent-acceptance run --repo <钉点> --base <fix^> --head <fix>` 对每任务跑一遍——金测试应在 base 失败、head 通过（工具第一次自证数据集质量）；
3. **粒度微调**：若某 fix 的测试依赖同 commit 的行为改动过大（如 C9 栈式重构），降级为"叙事素材"或拆分；
4. 30–50 条总量缺口：本轮 3 链共 29 条，放量轮从知识库候选池（click/httpie/pytest 等）补足。
