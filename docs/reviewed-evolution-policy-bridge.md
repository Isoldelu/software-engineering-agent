# Step 33 Reviewed Evolution-to-Policy Bridge

## 目的

Step 25 已能发现失败、生成配置候选并完成 Shadow；Step 23 已有版本化灰度和回滚，但此前两条链路没有直接、可审计的连接。Step 33 只允许人工批准且 Shadow 通过的 Evolution Candidate 经显式发布进入 Policy 控制面。

```text
Mined Failure -> Candidate -> Shadow/Regression -> Human Approve
-> Schema Translation -> Policy Validation -> SHA-256 Digests
-> Immutable Bridge Record -> Versioned Rollout Policy
-> Promote or Rollback
```

## 支持资产

| Evolution Asset | Policy 配置 | 运行时作用 |
|---|---|---|
| `router_rule` | `rules` | 在灰度 cohort 中优先选择指定 Tool |
| `query_alias` | `aliases` | Planner 前进行大小写无关的实体别名改写 |
| `retriever_weights` | `retriever` | 为 RAG Tool 注入 Hybrid 模式与权重 |

新配置与当前 stable Policy 合并，因此连续批准的资产不会覆盖其他已发布类型。Router Rule 按 `hook_id` 替换，Alias 按键更新，Retriever 配置整体替换。

## 安全门禁

1. Candidate 必须为 `approved`，并包含人工 reviewer。
2. `shadow_evaluation.passed` 必须为 true。
3. `EvolutionConfigValidator` 与 `PolicyConfigValidator` 必须同时通过。
4. `released_by` 必填，API 发布要求 admin。
5. Candidate/Config 分别生成 SHA-256 摘要，写入 Policy metadata 和 Bridge Record。
6. 相同 Candidate 与相同灰度参数重放返回同一 Policy；参数漂移返回冲突。
7. 同一时刻仍只允许一个 rollout Policy。
8. 回滚恢复父 Policy，并把来源 Evolution Candidate 标记为 inactive。

`POST /evolution/candidates/{id}/activate` 继续固定拒绝。Bridge 是人工控制的发布路径，不是 Agent 的自发布能力。

## 持久化与并发

Bridge 使用 `evolution_policy_bridge` 命名空间保存不可变映射。Policy Repository 在同一写租约内执行 source-id 去重、版本分配和 rollout 建立；若 Policy 已创建而 Bridge 写入暂时失败，重试会复用相同 Policy 并补齐 Bridge，不产生新版本。

## API

```text
GET  /evolution/bridges
POST /policies/from-evolution/{candidate_id}
```

发布响应包含 `bridge`、`policy`、`created`、`idempotent_replay` 和当前 assignment state。审计记录只写 Candidate/Bridge/Policy 标识、角色和灰度比例，不写 Query、凭据或内部数据。

## 边界

- 不训练或更新模型参数。
- 不修改源码、测试、数据集、权限或发布门槛。
- 不自动 approve，不自动发起灰度。
- 离线 9/9、零回归仅代表冻结模拟评测。
- 真实 Provider A/B 仍需显式 API Key 和预算。
