# Software-Agent API Contract V1

## 1. 兼容策略

本文记录 Step 17 冻结的公开 API 契约。后续 Evidence、Citation、Verification 和 execution status 只能以向后兼容方式增加，不能删除已有字段或改变已有字段含义。

服务版本：`0.1.0`。

## 2. Agent Query

### `POST /agent/query`

请求：

```json
{
  "query": "query openssl version",
  "persist_trajectory": false
}
```

请求字段：

| 字段 | 类型 | 必填 | 当前语义 |
|---|---|---:|---|
| `query` | string | 是 | 软件工程自然语言问题 |
| `persist_trajectory` | boolean | 否 | 是否追加写入 `data/trajectories.jsonl`，默认 `false` |

响应字段：

| 字段 | 类型 | 当前语义 |
|---|---|---|
| `query` | string | 原始请求 |
| `intent` | string | Planner 识别的意图 |
| `selected_tool` | string | 单工具名称或 `hybrid_plan` |
| `answer` | string | 确定性结构化回答 |
| `used_tools` | string[] | 实际工具调用顺序，包含重复调用 |
| `tool_call_count` | integer | 实际工具调用次数 |
| `evidence` | string[] | 当前版本的证据来源路径集合 |
| `confidence` | string | 当前计划置信度等级 |
| `success` | boolean | 当前版本中所有 observation 是否为 success |
| `plan` | object[] | Planner 生成的执行步骤 |
| `trajectory` | object[] | planning、tool execution、answer generation 轨迹 |

Step 18 向后兼容新增字段：

| 字段 | 类型 | 当前语义 |
|---|---|---|
| `evidence_items` | object[] | 可定位到具体记录或文档 Chunk 的结构化 Evidence |
| `citations` | object[] | 引用当前 Evidence ID 的轻量 Citation |
| `evidence_count` | integer | 去重后的结构化 Evidence 数量 |
| `execution_status` | string | `success/partial_success/not_found/failed` 四态执行结果 |
| `verification` | object | 在线 Verifier 的 passed、score、issues、rules 和 repair_count |

兼容要求：以上 11 个字段必须保留。当前内部 `run_agent()` 还可能包含 `arguments`、`tool_schema_version`、`planner_source` 和可选 `memory`，但它们不属于 `AgentQueryResponse` V1 的公开响应字段。

### `POST /agent/query-with-plan`

在基础请求上增加：

```json
{
  "llm_plan": {
    "intent": "dependency_analysis",
    "tool": "dependency_analysis",
    "arguments": {
      "package": "openssl"
    }
  }
}
```

该接口复用 `AgentQueryResponse`，响应字段与 `/agent/query` 相同。

## 3. Health

### `GET /health`

```json
{
  "status": "ok",
  "service": "ai-software-engineering-agent"
}
```

## 4. Tool Metadata

### `GET /tools`

返回：

```json
{
  "tools": []
}
```

`tools` 中包含当前 Tool Schema。

### `GET /function-specs`

返回：

```json
{
  "functions": []
}
```

`functions` 中包含 Function Calling 兼容定义。

## 5. Evaluation Endpoints

| Method | Path | 用途 |
|---|---|---|
| GET | `/evaluation/run` | 标准 benchmark |
| GET | `/evaluation/summary` | 四套评测汇总 |
| GET | `/evaluation/bad-cases` | Challenge 与 Bad Case 分析 |
| GET | `/evaluation/robustness` | 模糊查询鲁棒性评测 |
| GET | `/evaluation/experiment` | Baseline 与优化实验 |
| GET | `/evaluation/evidence` | Evidence normalization 与 Citation coverage |
| GET | `/evaluation/verifier` | 注入错误、误拒绝和部分成功评测 |
| GET | `/evaluation/rag` | Legacy、BM25 与 Hybrid RAG 消融评测 |
| GET | `/evaluation/context` | 多轮实体、Session 隔离、Trace 与 Replay 评测 |
| GET | `/evaluation/feedback` | 受控 Feedback、候选 Replay 与回归门禁评测 |
| GET | `/evaluation/policy` | 策略版本、灰度分流和自动回滚评测 |
| GET | `/evaluation/provider` | Offline/Mock-Online 一致性与故障降级评测 |
| GET | `/evaluation/evolution` | 离线失败挖掘、聚类、候选影子评测与安全门禁 |
| GET | `/evaluation/control-plane` | 数据库持久化、API 角色和多 Worker 一致性门禁 |

`/evaluation/run` 的 V1 字段：

```text
benchmark
total
tool_routing_accuracy
task_success_rate
answer_grounding_accuracy
answer_accuracy
average_tool_calls
bad_cases
results
```

## 6. 页面入口

| Method | Path | 响应 |
|---|---|---|
| GET | `/demo` | HTML Agent Demo |
| GET | `/evaluation-dashboard` | HTML 评测 Dashboard |

Step 21 新增会话与 Trace 端点：

| Method | Path | 用途 |
|---|---|---|
| GET | `/sessions/{session_id}` | 查询任务上下文 |
| DELETE | `/sessions/{session_id}` | 清除任务上下文 |
| GET | `/traces/{trace_id}` | 查询 trace-v1 |
| GET | `/traces/{trace_id}/replay-input` | 重建原始与解析后输入 |
| POST | `/traces/{trace_id}/replay` | 在隔离 Session 中重放 |

Step 22 新增受控优化端点：

| Method | Path | 用途 |
|---|---|---|
| POST | `/feedback` | 提交绑定 trace_id 的反馈 |
| GET | `/feedback` | 查询 Feedback 记录 |
| POST | `/candidates/propose` | 达到阈值后生成配置候选 |
| GET | `/candidates` | 查询候选列表 |
| GET | `/candidates/{candidate_id}` | 查询候选、门禁和审核状态 |
| POST | `/candidates/{candidate_id}/evaluate` | 隔离 Replay 与 193 条回归 |
| POST | `/candidates/{candidate_id}/review` | 人工批准或拒绝 |
| POST | `/candidates/{candidate_id}/activate` | Step 22 固定返回 409，禁止激活 |

Step 23 新增策略发布端点：

| Method | Path | 用途 |
|---|---|---|
| GET | `/policies` | 查询 stable、rollout、版本列表与监控状态 |
| GET | `/policies/assignment/{session_id}` | 查询 Session 的确定性策略分配 |
| POST | `/policies/from-candidate/{candidate_id}` | 从 approved Candidate 创建版本并开始灰度 |
| POST | `/policies/{policy_id}/rollout` | 修改灰度比例 |
| POST | `/policies/{policy_id}/promote` | 将灰度策略提升为 stable |
| POST | `/policies/{policy_id}/rollback` | 手动回滚到父策略 |
| POST | `/policies/{policy_id}/deprecate` | 废弃非 stable 策略 |
| POST | `/policies/{policy_id}/monitor` | 写入成功率与延迟监控样本，触发门禁判断 |

Step 24 新增 Provider 端点：

| Method | Path | 用途 |
|---|---|---|
| POST | `/agent/query-provider` | 选择 auto/offline/openai Planner Provider；默认允许安全降级 |
| GET | `/providers/status` | 查询 Provider 可用性与公开配置，不返回 API Key |
| GET | `/evaluation/provider` | 运行双模式与故障注入评测，付费调用为 0 |

`/agent/query-provider` 在原 Agent Response 上增加 `provider`：requested/effective provider、model、latency、usage、fallback 和 error type。Provider 失败且 `allow_fallback=false` 时返回 HTTP 503，且不执行 Tool。

## 7. Tool Observation 契约

五个 Tool 当前均通过 `run(query: str) -> dict` 执行，公共字段为：

```json
{
  "tool": "tool_name",
  "status": "success | not_found",
  "query": "original or normalized tool query",
  "evidence": "source path or source path list"
}
```

当前业务字段：

| Tool | 成功结果主要字段 |
|---|---|
| PackageSearchTool | `result_type`, `result`, optional `release` |
| DependencyAnalysisTool | `package`, `dependencies`，或 `component`, `dependents` |
| VersionCompareTool | `package`, `old_version`, `new_version`, `changes` |
| ComponentMappingTool | `component`, `owners` |
| RAGRetrieverTool | `results`, `retriever_mode`, `message` |

Step 18 已在保留这些字段的前提下增加 `normalized_observation` 和 `evidence_items`。统一 Observation 包含 `status/result/evidence/error/metadata`。

Step 20 为每个 RAG result 保留 V1 的 `source/title/content/score/matched_terms`，并增加 `chunk_id/document_id/section/version/retriever_mode/rank/scores`。运行模式可由 `SOFTWARE_AGENT_RAG_MODE` 在进程启动前配置。

## 8. 错误和验证行为

- Pydantic 请求校验失败由 FastAPI 返回 HTTP 422。
- 业务无记录当前通过 HTTP 200 和 Tool `status=not_found` 表达。
- 新调用方应读取 `execution_status`；旧 `success` 布尔值继续保持原义。
- `session_id` 可选；未提供时响应会生成新 Session。提供同一 ID 时仅继承该 Session 的任务实体。
- Step 21 向响应新增 `session_id/trace_id/parent_trace_id/resolved_query/inherited_context/context/trace/policy_version/replayable`。
- Feedback 必须引用存在的 trace_id；Candidate 必须达到三条同类负反馈阈值。
- 候选即使 `approved` 也保持 `active=false`，不会改变 `/agent/query` 的默认 Router 行为。
- 只有 approved Candidate 可创建 Policy；进入 rollout 后 Candidate 才标记 active。
- 同一 `session_id` 在灰度配置不变时始终落入相同 cohort。
- Agent 响应和 trace-v1 的 `policy_version/policy_assignment` 是策略归因依据。
- 自动或手动回滚后新请求使用父策略，历史 Trace 仍保留原策略版本。
- 在线 Provider 默认关闭；`OPENAI_API_KEY` 不进入 API 响应、Trace 或日志字段。
- 在线输出必须先通过 Structured Output Schema 和本地 Plan Validator，才能进入 Tool Executor。
- `persist_trajectory=false` 时不写入 JSONL。
- Step 17 不新增网络调用、鉴权或外部 LLM 依赖。

Step 25 新增离线受控自进化端点：

| Method | Path | 用途 |
|---|---|---|
| POST | `/evolution/scan` | 扫描离线标注集，挖掘失败、聚类并生成 draft 配置候选 |
| GET | `/evolution/state` | 查询本轮失败、聚类、候选和安全边界 |
| POST | `/evolution/candidates/{candidate_id}/shadow-evaluate` | 隔离执行关联 Bad Case 与冻结回归集 |
| POST | `/evolution/candidates/{candidate_id}/review` | 人工 approve/reject，仍不激活 |
| POST | `/evolution/candidates/{candidate_id}/activate` | 固定返回 409，禁止候选自激活 |

Step 25 只生成 `router_rule/query_alias/retriever_weights` 三类配置资产。自动流程最高到 `pending_review`，不得修改源码、数据集、测试断言、权限和发布门槛。

Step 33 新增受审 Evolution-to-Policy 桥接端点：

| Method | Path | 用途 |
|---|---|---|
| GET | `/evolution/bridges` | 查询不可变的 Candidate-to-Policy 映射、摘要和发布归因 |
| POST | `/policies/from-evolution/{candidate_id}` | 将已人工批准且 Shadow 通过的 Evolution Candidate 翻译为版本化灰度 Policy |

发布请求包含 `rollout_percentage` 和 `released_by`。端点要求 admin；未批准、未通过 Shadow、配置越界、已有其他灰度或同候选参数漂移返回 HTTP 409，不存在的候选返回 404。相同候选和相同参数重复请求返回同一 Bridge/Policy，并以 `idempotent_replay=true` 表达，不创建新版本。`/evolution/candidates/{candidate_id}/activate` 仍固定拒绝，Agent 不能绕过受审发布端点自行激活。

Step 26 新增控制面状态端点：

| Method | Path | 用途 |
|---|---|---|
| GET | `/ready` | 检查进程及已配置控制面数据库是否可用 |
| GET | `/auth/status` | 返回鉴权启用状态、Header 和已配置角色，不返回 Key |
| GET | `/storage/status` | 返回 memory/sqlite/postgresql 后端和脱敏健康状态 |
| GET | `/evaluation/control-plane` | 运行持久化、CAS、租约、角色和跨 Worker 一致性评测 |

开启 `SOFTWARE_AGENT_AUTH_ENABLED=true` 后，调用方通过 `X-API-Key` 鉴权：

- `reader`：读取状态、工具、Trace 和评测。
- `operator`：增加 Agent 执行、Feedback、Replay、Scan 和 Shadow Evaluation。
- `admin`：增加 Review、Policy 发布/调整/回滚、Activate 尝试和 Session 删除。
- 缺失或非法 Key 返回 401，角色不足返回 403，启用鉴权但没有配置任何 Key 返回 503。

设置 `SOFTWARE_AGENT_DATABASE_URL` 后，Session、Trace、Feedback、Candidate、Evolution 和 Policy 状态写入共享控制面数据库。写操作通过 record version 执行 compare-and-swap；陈旧写入和租约冲突返回 HTTP 409。公开响应不得包含数据库密码或 API Key。

Step 27 新增生产运维端点，全部要求 admin：

| Method | Path | 用途 |
|---|---|---|
| GET | `/auth/keys` | 查询脱敏的数据库托管 Key 元数据 |
| POST | `/auth/keys/rotate` | 轮换角色 Key；新明文只返回一次 |
| POST | `/auth/keys/{key_id}/revoke` | 撤销 Key；禁止撤销最后一个可用 admin Key |
| GET | `/audit/events` | 查询有界、脱敏的鉴权与控制面审计事件 |
| GET | `/maintenance/retention/policy` | 查询当前数据保留周期 |
| POST | `/maintenance/retention/run` | dry-run 或执行有界分批清理 |

响应 Header `X-Agent-Worker-Pid` 用于压测确认请求实际分布到多个 Worker。Registry 与 Audit 不返回原始 Key、Key Hash、数据库凭据或请求正文。

Step 28 新增 `GET /metrics`，开启鉴权时要求 reader。Prometheus Label 只允许 method、route template、status、denial reason 和 retention namespace，不允许 Query、Session/Trace ID、Key fingerprint 或请求正文。`/storage/status` 的 `pool` 字段只返回脱敏连接池计数。

Step 34 将 `evolution_policy_bridge` 与 `policy_state` 声明为受保护命名空间。`GET /maintenance/retention/policy` 和 retention 执行结果都会返回 `protected_namespaces`；通用按时长清理不得删除不可变 Candidate-to-Policy 归因记录或当前/历史 Policy 状态。多 Worker 对同一 Candidate、相同参数并发发布时只允许创建一个 Policy/Bridge；后续请求返回同一映射并标记 `idempotent_replay=true`。如果 Policy 已创建但 Bridge 写入失败，重试必须复用该 Policy 并补写 Bridge，而不是创建新版本。

Step 35 将 Agent Query 的 `provider` 扩展为 `auto | offline | openai | deepseek`。`deepseek` 只有在 online 显式启用且 `DEEPSEEK_API_KEY` 存在时可用；否则沿用 deterministic fallback。DeepSeek JSON 输出必须继续通过本地 Tool allowlist、Plan Schema 和参数类型校验，不能因 Provider 返回合法 JSON 就直接获得 Tool 执行权。Provider 状态只返回 Key 是否配置，不返回 Key 内容；Trace 和响应仅保留脱敏 model、latency、usage、fallback 和 error type。

## 9. 契约验证

```bash
python -B -m pytest -q tests/contracts -p no:cacheprovider
python -B evaluation/baseline.py --check
```

契约测试不仅检查 HTTP/函数是否返回，还检查字段、状态、Tool 语义和代表性完整输出。
