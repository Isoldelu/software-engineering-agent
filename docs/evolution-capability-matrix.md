# 受控自进化能力矩阵

## 结论

当前项目**已经实现离线、配置级、受控自进化**，但没有实现在线自治学习或源码自修改。

最准确的表述是：

> 系统能够从标注评测失败中发现重复模式，生成有限类型的配置候选，并通过 Shadow 与冻结回归验证候选；候选不能自行激活，但人工批准后可经受审桥接进入版本化灰度与回滚。

## 已实现链路

| 环节 | 当前实现 | 证据 |
|---|---|---|
| 失败发现 | 重跑 Agent 与 RAG 标注用例，识别可复现失败 | `app/evolution/miner.py` |
| 根因聚类 | Router Miss、Entity Alias Miss、Retriever Rank Miss；最小支持数为 2 | `OfflineFailureMiner` |
| 候选生成 | Router Rule、Query Alias、Retriever Weights | `EvolutionCandidateFactory` |
| 安全校验 | 只允许配置变更，禁止源码、权限、数据集和自动激活 | `EvolutionConfigValidator` |
| Shadow 验证 | 关联失败用例与隔离执行环境 | `ShadowEvaluator` |
| 冻结回归 | Agent 候选回放 193 条；Retriever 候选回放 30 条 | `docs/offline-controlled-evolution.md` |
| 人工审核 | 自动状态最高为 `pending_review`；审批后仍为 `active=false` | `OfflineEvolutionService` |
| 策略工程 | 另有策略版本、稳定哈希灰度、监控和自动回滚 | `app/policy/` |
| 受审发布桥 | Approved Candidate 经 Schema Translation、摘要、幂等发布进入不可变 Policy | `app/evolution/bridge.py` |
| 运行时生效 | Router Rule、Query Alias、Retriever Weights 均由分配到的 Policy 控制 | `app/policy/engine.py`、`app/agent/workflow.py` |

当前实验重新执行结果：

```text
Mined failures: 9
Root-cause clusters: 3
Configuration candidates: 3
Fixed linked failures: 9
Regressions: 0
Paid API calls: 0
Result: passed
```

## 尚未实现

| 能力 | 状态 | 影响 |
|---|---|---|
| 在线持续学习 | 未实现 | Miner 当前读取标注 Benchmark，不会自动消费全部线上 Trace 并持续改策略 |
| 模型训练 | 未实现 | 没有 Fine-tuning、RL、策略梯度或参数更新 |
| 源码自修改 | 明确禁止 | Candidate 不能编辑 Python、测试、数据集、权限和发布门禁 |
| 自动上线 | 明确禁止 | Evolution Candidate 的激活接口固定返回拒绝 |
| Evolution 到 Policy 受审桥接 | 已实现 | 不复制为 Feedback Candidate；保留独立模型，通过不可变 Bridge Record 映射到 Policy Version |
| 真实 Provider 驱动优化 | 未执行 | 当前循环为离线确定性实验，Paid API Calls=0 |

## 关于策略发布的精确边界

项目已经连通：

1. Offline Evolution Candidate 的发现、Shadow、回归和人审。
2. Evolution Candidate 的人工 approve、Schema Translation、配置合并和摘要校验。
3. Feedback/Evolution 两类来源共用的版本化灰度、监控、提升和回滚控制面。

Evolution Candidate 不会自动转换成 Feedback Candidate，也不会自动进入灰度。更准确的说法是：

> 自进化验证闭环和策略发布控制面已经通过显式受审桥接连通；只有人工批准、Shadow 通过且配置校验通过的候选，才能由 admin 发起灰度，异常时按 Policy Version 回滚。

## 面试可说与不可说

可以说：

> 我实现了受控自进化：离线挖掘失败、聚类根因、生成配置候选、Shadow 验证、冻结回归和人工审核。实验发现 9 个失败，生成 3 类候选，修复 9 个且零回归，自动激活被禁止。

进阶表述：

> Step 33 又补上 Reviewed Evolution-to-Policy Bridge。三类 approved 配置可以经 Schema Translation 和双摘要校验生成不可变 Policy Version，按 Session 稳定灰度；重复请求幂等，回滚会恢复父策略并同步候选状态。Agent 仍不能自行发布。

不要说：

- Agent 会自动修改自己的代码。
- 系统已经实现线上持续学习。
- 项目训练了 RL 或微调模型。
- Evolution Candidate 会自动发布到生产。
- 冻结集 100% 代表开放领域泛化能力。

## 下一阶段建议

Reviewed Evolution-to-Policy Bridge 已完成。下一项应验证更接近生产的发布治理：

```text
Bridge API
-> PostgreSQL multi-Worker idempotency
-> concurrent release / rollback fault injection
-> audit export and retention proof
-> optional real Provider A/B under explicit budget
```

仍不应加入源码自修改、自动降低评测门槛或无人工审批上线。
