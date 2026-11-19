# P3 实验设计（runner 实现的规范依据）

> 2026-11-16 定稿。经用户裁决：消融按 v2 两臂、agent = OpenCode + Aider、先试点后补中文链。
> 本文是 `experiments/` runner 的实现规范；与 RESEARCH_PLAN.md 冲突时以本文为准（并回写）。

## 一、臂定义（冻结）

| 臂 | 门控 | 修复轮 | 反馈内容 | 回答 |
|----|------|--------|----------|------|
| **A0** baseline | 无 | 0 | 无 | RQ1 衰减复现 + DIR |
| **A1** gate-only | 有效性验证 | 1 | 金测试失败清单（仅用例名）+ 证据判定摘要（VALID/PRE-PASS/BROKEN 计数） | RQ3 |
| **A-full** | 有效性验证 | 1 | A1 全部 + 变异幸存者报告（≤5 条幸存突变描述） | RQ2, RQ3 |

- 消融 = A1 vs A-full 的信息量差（正面回答 arXiv:2609.09315 成本质疑）。
- 阳性对照：BOBA 一位信号 (+8pt) 应 ≤ A1 的恢复幅度。
- 实验锁定 **agent-acceptance v1.0.0**（C1 冻结版；G11 修复 cd38f84 在其后的 main，不进实验——如需纳入须升版本并记 ADR）。

## 二、任务与链的执行语义

### 单任务
1. 工作树 = 任务钉点（链首任务 = `F1^`；后续任务 = **链状态树**，见下）；
2. agent 收到：任务陈述（issue 正文或策划描述）+ 仓库上下文；**不见金测试**；
3. agent 产出：代码修改（+ 自写测试，按真实贡献者行为）；
4. 评测：金测试（holdout）跑于 agent 工作树 → `ACCEPT`（金测试中与本任务相关的用例全过）/ `REJECT`；同时 agent 自写测试过门（A1/A-full）；
5. A1/A-full 且金测试失败 → 携带反馈进入 1 轮修复 → 复评。最终 ACCEPT 与否定格。

### 链（缺陷继承的载体）
- 链状态**逐任务携带**：τ(i+1) 的起点 = τi 结束时的 agent 工作树（ACCEPT 与 REJECT 都携带——继承的缺陷正是 RQ1 的测量对象）；
- 链完成 `CCR` = 全部任务 ACCEPT 的链比例；任务 `TCR` = 全体任务 ACCEPT 池化比例；
- 已知风险：上游 `Fi^` 与链状态树之间可能夹着无关上游提交，金测试可能因此失败——**归因阶段用确定性 trace 规则区分**（失败节点模块最后被 τj 修改→继承类；否则环境/依赖类）。

### 随机性与重复
- 每 (agent, 模型档, 臂) 组合 ≥3 独立重复；同组内任务顺序、种子固定；温度按 agent 适配器默认（记录于每次 run 元数据）。

## 三、agent 适配器契约

```
Adapter.run(workdir, task_prompt, model) -> AdapterResult {
    exit_code, transcript_path,
    tokens_in, tokens_out,   # 仅 adapter 官方用量报告（token_source=adapter）
    seconds,                 # agent 墙钟
}
```
- OpenCode：非交互 `run` 模式；Aider：`--message` 单轮 + `--yes-always`。
- 两 agent 版本钉死后记录在 run 元数据；实验中途不升级。

## 四、指标与日志

- `CCR`/`TCR`/`DIR`/静默漏检率/token 成本/墙钟成本——定义见 RESEARCH_PLAN 指标表；
- **全量原始日志入库**（约束：负面结果不修饰）：`experiments/runs/<run_id>/` 每任务一个目录：`meta.json`、`transcript`、`diff.patch`、`gold_result.json`、`gate/`（evidence.json）、修复轮目录 `repair/`；
- run_id = `{agent}-{model}-{arm}-{chain}-r{rep}`。

## 五、预算与执行顺序

1. **试点校准**（本阶段）：1 链 × (1 agent × 1 模型 × A0) 全任务实跑 → 单任务成本 → 外推全矩阵 → 对照 ¥3,000 出削减方案（候选：A-full/A1 仅 10 链子集、模型档位降配、重复数 3）；
2. 中文链（1–2 条）按放量 SOP 并行补齐，纳入 RQ1 正式跑；
3. RQ1 → RQ2/RQ3 顺序执行，每批运行前报预估成本。

## 六、开放问题（不阻塞试点）

1. 任务陈述来源：issue 正文可用则直接用；PR 型任务（无 issue）用策划描述改写——改写文本进数据集仓库留痕；
2. ~~模型档位具体型号~~ **已定（2026-11-16）**：本机 `DEEPSEEK_API_KEY` 有效，两档 = `deepseek-flash`（快档）/ `deepseek-v4-pro`（强档），OpenCode 与 Aider 同 key 同档位（保证"仅差协议开关"约束在模型维度也成立）；模型版本以 API 侧当日快照为准并记入 run 元数据；
3. agent 自写测试在 A0 的处理：收集但不反馈（用于静默漏检率的辅证）。
