# 受控自进化能力矩阵

## 结论

当前项目**已经实现离线、配置级、受控自进化**，但没有实现在线自治学习或源码自修改。

最准确的表述是：

> 系统能够从标注评测失败中发现重复模式，生成有限类型的配置候选，并通过 Shadow 与冻结回归验证候选；候选必须经过人工审核，不能自行激活。

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
| Evolution 到 Policy 直接桥接 | 未实现 | Evolution Candidate 与可发布 Policy Candidate 使用不同模型和 Repository |
| 真实 Provider 驱动优化 | 未执行 | 当前循环为离线确定性实验，Paid API Calls=0 |

## 关于策略发布的精确边界

项目已经分别实现：

1. Offline Evolution Candidate 的发现、Shadow、回归和人审。
2. Feedback Policy Candidate 的版本化、20% 灰度、监控和自动回滚。

但目前没有把第 1 类 Candidate 直接转换成第 2 类 Candidate 的受审桥接服务。因此不能表述为“离线发现的候选已经自动进入灰度发布”。更准确的说法是：

> 自进化验证闭环和策略发布控制面均已实现，但两者之间仍需要显式、可审计的候选转换步骤。

## 面试可说与不可说

可以说：

> 我实现了受控自进化：离线挖掘失败、聚类根因、生成配置候选、Shadow 验证、冻结回归和人工审核。实验发现 9 个失败，生成 3 类候选，修复 9 个且零回归，自动激活被禁止。

不要说：

- Agent 会自动修改自己的代码。
- 系统已经实现线上持续学习。
- 项目训练了 RL 或微调模型。
- Evolution Candidate 会自动发布到生产。
- 冻结集 100% 代表开放领域泛化能力。

## 下一阶段建议

下一项真正的自进化增强应是 **Reviewed Evolution-to-Policy Bridge**：

```text
Approved Evolution Candidate
-> Schema Translation
-> Policy Validator
-> Immutable Policy Version
-> Shadow / Canary
-> Metrics Gate
-> Promote or Rollback
-> Audit Event
```

桥接必须保留人工确认、幂等性、审计记录和一键回滚，仍不允许源码自修改。
