# Software Engineering Agent 模拟面试指南

## 90 秒版本

> 这是一个基于公开风格模拟数据复现的 AI4SE Agent，不包含华为内部数据。系统面向 Package、Dependency、Version、Component 和研发文档检索，由 Planner 组合五个领域工具，结果统一进入 Evidence、Citation、Verifier 和可回放 Trace。以 nginx 版本变化和依赖为例，Planner 会组合三个工具，而不是只做一次 RAG。项目建立了 193 条冻结评测和离线 Proxy Baseline，关键词 Router 在挑战集上为 61.76%，优化后达到冻结集 100%。我还实现了受控自进化：离线挖掘 9 个失败，生成 Router、Alias 和 Retriever 三类配置候选，Shadow 修复 9 个且零回归，但候选不能修改源码或自动激活。GitHub Actions 已验证 134 项测试、Docker 和 PostgreSQL 多 Worker 门禁。真实 Provider A/B 尚未执行。

## 3 分 30 秒版本

### 1. 问题与定位

研发资产信息分散在软件包、依赖关系、版本记录和非结构化文档中。这个项目使用公开风格模拟数据，复现实习中接触的软件资产检索、解析自动化和 Agent 工具化方法，不包含企业内部数据。

### 2. Agent 架构

用户 Query 先进入多轮 Context，再由 Planner 和 Router 生成单工具或 Hybrid Plan。五个工具分别处理 Package Search、Dependency Analysis、Version Compare、Component Mapping 和 Hybrid RAG。工具结果不会直接拼成答案，而是标准化为 Evidence 与 Citation，经确定性 Verifier 判断成功、部分成功或失败，最后记录可回放 Trace。

### 3. 复合任务

输入“查一下 nginx 的版本变化和依赖”时，Planner 组合 Package、Dependency、Version 三个工具。结果包含 3 条 Evidence、3 条 Citation，Verifier 与 Trace 均通过。多工具规划的意义不是增加调用次数，而是把复合问题拆成可验证子任务。

### 4. 评测与优化

项目使用 Tool Accuracy、Task Success、Answer Accuracy、Grounding 和平均调用次数评测。关键词 Router 在挑战集上为 61.76%，加入 Alias Mapping、Tool Description、Hybrid Planner 和 Bad-case Regression 后达到冻结集 100%。DirectLLMProxy 与 RAGOnlyProxy 是离线可复现基线，不是真实商业模型 A/B。

### 5. 受控自进化

OfflineFailureMiner 重跑标注用例，识别 Router、Alias 和 Retriever 三类重复失败，最小聚类支持数为 2。系统生成有限类型的配置候选，在隔离环境执行关联 Shadow 和冻结回归。实验挖掘 9 个失败，生成 3 个候选，修复 9 个且零回归。候选最高自动状态是 `pending_review`，不能修改源码或自行激活。

### 6. 工程交付与边界

FastAPI、PostgreSQL、鉴权、审计、Prometheus、备份恢复、Docker 和多 Worker 路径已经建立。GitHub Actions 当前验证 134 项测试。策略层另有版本化、灰度和自动回滚，但 Evolution Candidate 到可发布 Policy Candidate 还缺显式桥接。真实 Provider A/B 仍等待 API Key 与预算。

## 高频技术追问

### 你的项目到底有没有自进化？

有，但限定为**离线配置级受控自进化**。它会发现失败、聚类根因、生成配置候选并验证；不会训练模型、修改源码或跳过人工审核。更完整的边界见 `docs/evolution-capability-matrix.md`。

### 为什么不允许自动激活？

评测集可能存在覆盖盲区，单一指标提升也可能带来安全、延迟或长尾回归。候选必须经过固定回归、人审和独立发布控制面，才能控制变化范围并保留责任链。

### 为什么称为 Agent，而不是 RAG？

RAG 只是一个工具。Agent 还负责 Context、意图路由、多工具规划、参数解析、环境反馈、Evidence 聚合、Verifier 和 Trace；复合任务可以组合结构化工具与 RAG。

### 193/193 是否说明模型泛化很好？

不能。它只说明当前确定性策略在冻结模拟数据集上满足预期，不能外推到开放领域。Challenge Set、Bad-case 和真实 Provider A/B 分别验证不同风险。

### 为什么使用离线 Proxy Baseline？

它提供零成本、稳定、可重复的工程对照，适合验证工具增强的相对价值。但它不能代替 GPT、Claude 或其他真实 Provider 的质量、延迟和成本实验。

### Evolution Candidate 能直接灰度吗？

目前不能。Offline Evolution 与 Feedback Policy 使用两类 Candidate 和 Repository。灰度与回滚能力已实现，但还需要 Reviewed Evolution-to-Policy Bridge 才能把两条链路连起来。

### 如何避免 Bad Case 把策略带偏？

要求同类问题达到最小支持数，只允许白名单配置类型，先跑关联用例，再跑冻结回归，并检查核心分数、回归数和延迟；候选不能自行激活。

### 为什么使用确定性 Verifier？

关键事实来自结构化工具和检索证据，可以用规则验证覆盖、引用和任务完成状态。这样结果可复现，也不会再用一个 LLM 去模糊判断另一个 LLM。

### PostgreSQL 压测数字能代表生产性能吗？

不能。100/100 和 40/40 是并发一致性、Worker 替换与恢复门禁，不是容量上限或 SLA。生产性能还需要更长时间、更大负载和真实资源配额。

### 下一步最有价值的改进是什么？

不使用付费 API 时，优先实现受审 Evolution-to-Policy Bridge；预算明确后，再用固定 Query Set 做真实 Provider 的质量、延迟、成本和回退 A/B。

## 自评分标准

| 维度 | 通过标准 |
|---|---|
| 定位 | 20 秒内说清 AI4SE、模拟数据和个人复现 |
| 架构 | 能说明 Planner、Tools、Evidence、Verifier、Trace |
| 证据 | 至少给出一个复合 Query、一个评测提升和一个 CI Run |
| 自进化 | 同时说出已实现链路与不能自动激活 |
| 边界 | 主动说明冻结集、离线 Proxy、Provider 和性能边界 |
| 时间 | 90 秒版不超过 100 秒；标准版控制在 190-230 秒 |
