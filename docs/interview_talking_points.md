# Interview Talking Points

## 项目身份边界

必须始终区分两段经历：

```text
华为真实经历：
在网络设备研发环境中参与软件资产检索、解析自动化和 Agent 工具化探索。

个人复现项目：
为验证 Agent 方法论，基于模拟软件资产数据搭建 Software Engineering Agent。
```

不要把个人 Demo 的代码、指标、PostgreSQL CI 或自进化实验说成华为内部系统结果。

## 30 秒版本

> 我基于模拟软件资产数据实现了一个 AI4SE Agent，用来解决包信息、依赖、版本变化、
> 组件归属和研发文档分散的问题。系统通过 Router 和 Hybrid Planner 组合五个专业工具，
> 再用 Evidence、Citation 和 Verifier 保证答案可追溯。我建立了 193 条冻结评测和受控
> Bad-case Loop，路由准确率从 61.76% 提升到 100%；服务层支持 FastAPI、PostgreSQL
> 多 Worker、鉴权、审计、指标和故障恢复。所有数据均为模拟数据，真实 Provider A/B
> 因预算未明确暂未执行。

## 2 分钟版本

> 项目的起点是一个工程判断：结构化的软件资产问题并不适合全部交给 RAG。比如包版本、
> 正反向依赖和组件归属应该由确定性工具查询，发布说明和手册才适合检索。因此我设计了
> Package、Dependency、Version、Component 和 RAG 五个工具，并让 Planner 对复合问题
> 进行多步拆解。
>
> 工具返回后不会直接拼答案，而是先归一化为 Evidence 和 Citation，再由确定性 Verifier
> 检查事实覆盖与工具状态；部分步骤失败时返回 partial success，而不是假装全部成功。
> 每次执行都会生成带 Context、工具序列、证据、策略版本和隐私边界的 Trace，可用于回放
> 和定位 Bad Case。
>
> 评测方面，我冻结了 193 条标准、Challenge、鲁棒性和大规模用例，并做 DirectLLMProxy、
> RAGOnlyProxy 和 Agent 对比。通过 Alias、参数归一化和 Hybrid Planner 优化，路由准确率
> 从 61.76% 提升到 100%。反馈不会让 Agent 自动改源码，而是生成白名单配置候选，经过
> Shadow Evaluation、全量回归和人工审核后才能灰度发布，异常时回滚父策略。
>
> 工程层面，FastAPI 控制面支持 PostgreSQL 共享状态、CAS、Lease、API Key 轮换、Audit、
> Retention、Prometheus 和备份恢复。GitHub Actions 的真实 PostgreSQL 测试中，双 Worker
> 100 次请求和替换 Worker 后 40 次请求均零 5xx，6 类故障门禁全部通过。

## 5 分钟展开顺序

1. **问题建模**：结构化资产与非结构化文档需要不同工具，不应统一塞进向量库。
2. **Agent 执行**：Context -> Router/Planner -> Tools -> Evidence -> Verifier -> Answer -> Trace。
3. **复杂任务**：展示 `查一下 nginx 的版本变化和依赖` 如何组合三个结构化工具。
4. **评测优化**：解释 193 条冻结集、三类 Baseline、61.76% 到 100% 的 Bad Case 闭环。
5. **受控自进化**：只生成配置候选，禁止改源码和自动激活，必须回放、Shadow、人工审核。
6. **工程交付**：FastAPI/PostgreSQL、多 Worker 一致性、Auth/Audit/Metrics/Backup。
7. **边界**：模拟数据、离线 Proxy、CI 功能压测、真实 Provider 未测。

## 最值得展示的一条 Query

```text
查一下 nginx 的版本变化和依赖
```

讲解顺序：

```text
Query
-> Hybrid Planner
-> PackageSearchTool
-> DependencyAnalysisTool
-> VersionCompareTool
-> Evidence/Citation
-> Verifier
-> Structured Answer
-> Replayable Trace
```

不要只读最终答案，重点指出 `used_tools`、`plan`、`evidence_items`、`verification` 和
`trace_id`，这些字段才体现 Agent 工程设计。

## 核心实验故事

### 为什么不只做 RAG

```text
DirectLLMProxy task success: 22.94%
RAGOnlyProxy task success:   57.06%
Agent task success:         100.00%
```

回答时补充：这是模拟数据上的离线 Proxy 对比，用于验证系统方法，不代表真实模型排名。

### 如何做 Bad Case 优化

```text
LegacyKeywordRouter tool accuracy: 61.76%
OptimizedAgent tool accuracy:      100.00%
Absolute improvement:              +38.24%
```

优化内容包括 Alias Mapping、工具描述、参数归一化、复合意图规划和模糊 Query 鲁棒性测试。

### 一次真实的发布 Bad Case

v1.0 RC 曾因微基准延迟抖动让候选错误进入 `rejected`。定位到纯 15% 相对延迟门禁后，
将统计从 mean 改为 median，并增加 0.5 ms 噪声下限，同时保留真实性能退化拦截。修复后
128 项测试、Docker 和 PostgreSQL 三个 CI Job 全绿。

## 高频追问

### 这是不是关键词匹配

第一版包含关键词路由，后续增加 Alias、参数归一化、复合意图 Planner、LLM 风格计划校验
和可选 Provider Adapter。确定性 Router 仍保留为零成本、可回归的默认路径，而不是伪装成
大模型推理。

### 为什么不用纯 RAG

RAG 适合发布说明和手册，但精确包版本、依赖边和组件归属是结构化事实。将这些任务交给
专业工具更容易验证，也能明确区分“没查到”和“工具失败”。Hybrid Agent 根据问题组合
结构化 Tool 与 RAG。

### 你说的自进化是什么

是受控离线优化，不是 Agent 自己修改代码。Trace 和 Feedback 产生 Bad Case，系统聚类
根因并生成白名单配置候选；候选必须经过 Shadow、冻结集回归、人工审核和策略灰度，任何
门禁失败都不能激活。

### 为什么 100% 不代表过拟合

100% 只描述当前模拟冻结集。项目通过独立 Challenge、模糊 Query、Multi-turn、RAG 和
故障注入扩展覆盖，但数据规模和领域仍有限。真正泛化能力需要外部数据集和真实 Provider
A/B，因此不会把该数字表述为通用模型能力。

### 是否调用了真实 LLM

当前默认模式没有付费调用。项目实现了 OpenAI Responses 风格的结构化 Planner Adapter、
Schema 校验、Timeout 和 Fallback，并用 Mock Online 做计划一致性测试；真实质量、Token、
延迟和成本仍待 API Key 与预算明确后测量。

### Evidence 和 Citation 与普通日志有什么区别

Evidence 是回答事实的结构化来源，Citation 把答案声明关联到具体资产记录或文档 Chunk；
Trace 则记录执行过程、工具序列、策略和回放输入。三者分别解决事实依据、展示引用和过程
复现问题。

### Partial Success 有什么价值

复合任务中可能只有一个工具失败。系统保留成功步骤的 Evidence，同时明确失败步骤和缺失
字段，Verifier 将状态标为 partial success。这样比全部失败或编造缺失结果更适合研发场景。

### 多 Worker 如何保持一致

PostgreSQL 保存 Session、Trace、Feedback、Candidate、Policy 和 Key 状态；Revision CAS
拒绝 stale write，TTL Lease 串行化策略发布与 Evolution Scan，Migration 使用 checksum 和
advisory lock。每 Worker 使用有界连接池，Prometheus 使用 multiprocess 聚合。

### 如何证明工程能力不是只写了接口

GitHub Actions Run `33314875879` 同时运行 138 项测试、Docker Build 和真实 PostgreSQL
集成。双 Worker 首轮 100/100、替换 Worker 后 40/40 均零 5xx；数据库停机时 readiness
返回 503，恢复后返回 200；Fault Injection 6/6，Backup Restore 2/2。

### 下一步最有价值的工作

小预算真实 Provider A/B，重点测计划合法率、Task Success、P95 Latency、Token 和单任务
成本；其次是引入外部公开软件资产数据集，验证冻结集之外的泛化能力。

## 不要越过的表述边界

- 不说“华为内部数据”“华为线上系统”“华为项目达到 100%”。
- 不说“训练了 RL”或“Agent 自动修改和发布代码”。
- 不把 DirectLLMProxy 称为真实 GPT/Claude/Gemini 测试。
- 不把 GitHub Runner 的 100/40 请求结果称为生产 QPS 或 SLA。
- 不说 FAISS、LangGraph 或真实 Provider 已完成，除非对应实现和实验后来确实落地。
- 不展示 API Key、Audit 原文、Trajectory 原始 Query 或任何企业内部资料。

## 最后一句

> 这个项目让我真正理解的不是“怎么调用一个 LLM”，而是如何把 Agent 的工具选择、事实
> 依据、失败语义、执行轨迹、优化候选和策略发布都变成可测试、可回滚的工程契约。
