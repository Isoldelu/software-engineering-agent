# Software-Agent 下一阶段改造计划（Roadmap V2）

## 1. 规划结论

当前项目已经完成 Step 1-16，具备五类工具、确定性 Router/Planner、Hybrid Plan、轻量 RAG、轨迹持久化、FastAPI、浏览器 Demo 和 193 条离线评测。下一阶段不再以“增加更多工具”为主，而是把现有 Demo 升级为：

> 一个具有统一证据、在线校验、部分成功语义、可回放 Trace，并能通过全量评测和人工审批进行受控策略优化的软件工程 Agent。

本轮改造分为 7 个验收关口，对应 Step 17-23。每个关口都必须同时交付代码、测试、评测、文档和演示，上一阶段未通过验收时不进入下一阶段。

## 2. 当前基线与真实差距

### 已经具备

- 五个可执行工具：Package、Dependency、Version、Component、RAG。
- 单工具及多工具规划，支持 release、依赖、版本等组合任务。
- JSONL trajectory、Bad Case/Robustness/Large Benchmark 和评测 Dashboard。
- 193 条评测当前全部通过。
- 离线代理基线：DirectLLMProxy、RAGOnlyProxy、Agent。
- FastAPI、CLI、Demo 页面和面试材料。

### 尚未具备

| 能力 | 当前实现 | 目标实现 |
|---|---|---|
| Evidence | 来源路径字符串 | 统一 Evidence/Citation 对象及稳定 ID |
| 执行状态 | `success: bool` 为主 | `success/partial_success/not_found/failed` |
| Verifier | 评测时离线检查 | 返回答案前执行确定性在线校验 |
| RAG | 词元重叠与来源加权 | BM25 + 现有召回 + RRF + 确定性 Reranker |
| Trajectory | 无 trace/session/policy/latency | 可关联、可重放的完整 Trace |
| 多轮 | 单轮 Query | release/package/architecture 实体继承 |
| Bad-case Loop | 生成离线优化建议 | 反馈归因、候选策略、全量回放、审批 |
| 策略管理 | 规则写在 Python 中 | 配置型策略版本、激活、废弃、回滚 |

注意：当前 100% 指标来自模拟数据上的封闭离线评测，DirectLLMProxy 和 RAGOnlyProxy 也是可复现的离线代理基线。后续文档和面试中继续保留这个边界，不把结果表述为真实线上 LLM 效果。

## 3. 总体顺序

```text
Step 17 基线与兼容保护
-> Step 18 Evidence/Citation
-> Step 19 Verifier/部分成功
-> Step 20 Hybrid RAG
-> Step 21 Context/Trace
-> Step 22 Feedback/受控优化闭环
-> Step 23 策略版本化与工程交付
```

受控自进化不是单独插入的捷径。它依赖 Step 18 的证据、Step 19 的校验、Step 21 的 Trace，最终在 Step 22-23 中形成闭环。

## 4. 里程碑计划

### Step 17：架构基线与兼容保护（下一步立即执行）

当前问题：已有 193 条评测，但缺少冻结的机器可读基线、API 契约测试和 Golden Output。直接重构 Evidence 或 Workflow 容易出现“原评测仍通过，但接口语义已经变化”的隐性回归。

新增原因：先固定当前行为，后续所有优化才能回答“改了什么、是否回归、是否还能复现”。

交付闭环：

- 代码：增加一键生成/校验基线脚本，不改变现有业务行为。
- 测试：为五个 Tool 增加成功、边界、失败契约测试；为单工具、Hybrid、not_found 增加 Golden 测试。
- 评测：保存 `evaluation/baseline-v1.json`，记录 193 条结果、环境和指标。
- 文档：新增 `docs/architecture-v2.md`、`docs/api-contract.md`。
- 演示：一条命令重放基线并输出差异；原 `/agent/query` 字段保持不变。

验收门槛：

- 现有测试全部通过，193 条评测无下降。
- `/agent/query` 当前字段及语义保持兼容。
- 新增字段只能是可选或向后兼容字段。
- 基线可通过一条命令复现，差异由程序判断而非人工查看。

预计工作量：1-2 天。

### Step 18：Evidence 与 Citation 事实证据层

当前问题：现有 `evidence` 主要是文件路径，无法证明答案中的某个包名、版本号或依赖边具体来自哪条记录。

新增原因：Verifier、引用覆盖率和后续自进化都必须建立在结构化、可定位的事实证据上。

交付闭环：

- 代码：新增 Evidence、Citation、ToolObservation、EvidenceNormalizer；五个 Tool 输出统一 Observation。
- 测试：稳定 ID、去重、not_found 无伪引用、Hybrid 多源合并测试。
- 评测：新增 citation coverage、normalization success、unsupported structured facts 指标。
- 文档：补充证据 Schema、来源映射和 API 兼容规则。
- 演示：Demo/API 展示答案、引用摘要和可定位证据。

验收门槛：Citation coverage >= 95%，Evidence normalization = 100%，unsupported structured facts = 0，原 193 条继续通过。

预计工作量：3-4 天。

### Step 19：确定性 Verifier 与部分成功语义

当前问题：Agent 生成答案后直接返回；Hybrid 中只要一个子任务没有 `success`，整体布尔值就可能失真，也没有在线拦截伪造版本、错误依赖方向或无效引用。

新增原因：把“评测后发现错误”前移为“响应前阻止错误”，并准确表达多工具任务的部分完成状态。

交付闭环：

- 代码：实现至少 8 条确定性校验规则、VerificationResult、一次性确定性修复和四态执行状态聚合。
- 测试：为 unsupported claim、错误依赖、缺失步骤、无效 Citation、not_found 等每类 Issue 建立单测。
- 评测：增加注入错误集和 partial-success 分类集。
- 文档：记录规则、Issue Schema、修复边界和状态语义。
- 演示：展示一次错误草稿被校验阻断或修复，以及一个 partial_success Hybrid 请求。

验收门槛：注入错误检测 >= 95%，误拒绝 <= 5%，partial-success 分类 >= 95%，无效引用检测 = 100%，修复最多一次。

预计工作量：3-4 天。

### Step 20：Hybrid RAG 检索升级

当前问题：现有检索器基于词元重叠和简单来源加权，缺少标准 Chunk ID、BM25、融合排序以及 Recall/MRR 指标。

新增原因：让非结构化研发文档检索具备可解释、可量化、无外部 API 也可复现的提升。

交付闭环：

- 代码：标准 Chunk、BM25、现有召回器适配、RRF、确定性 Reranker，并允许配置切换旧/新检索器。
- 测试：中英文、空查询、过滤、排序稳定性、多文档冲突和无答案测试。
- 评测：建立带相关 Chunk 标注的 RAG 集，计算 Recall@3、Recall@5、MRR 和无答案识别率。
- 文档：记录检索链路、分项得分、参数和消融实验。
- 演示：Dashboard 对比旧 Retriever、BM25 和 HybridRetriever。

验收门槛：Recall@3 >= 90%，Recall@5 >= 95%，MRR >= 0.85，Citation correctness >= 95%，Hybrid 核心指标不低于旧检索器。

预计工作量：4-5 天。

### Step 21：多轮 Context 与增强 Trace

当前问题：trajectory 已能记录执行步骤，但缺少 trace_id、session_id、策略版本、步骤延迟、Verification 和可重放输入；系统也不支持跨轮实体继承。

新增原因：为多轮研发查询提供上下文，同时给 Feedback、归因、Replay 和审计建立统一数据基础。

交付闭环：

- 代码：AgentContext、Session Repository、Trace Recorder、Replay Reader；只保存任务必要实体，不记录内部 Thought。
- 测试：实体继承、跨 Session 隔离、清除 Session、容量限制、Trace 重建测试。
- 评测：新增多轮一致性和跨会话污染评测。
- 文档：记录 Context/Trace Schema、隐私边界和保留策略。
- 演示：连续执行“查 1214 的 openssl -> 它的依赖 -> 再比较版本”，并按 trace_id 重放。

验收门槛：多轮实体一致性 >= 95%，跨 Session 泄漏 = 0，Trace 完整率 = 100%，Replay 输入重建 = 100%。

预计工作量：3-4 天。

### Step 22：Feedback 与受控 Bad-case Loop

当前问题：当前 Bad Case 模块能离线分类并给出文字建议，但不能接收用户反馈、生成配置型候选、隔离回放或执行人工审批。

新增原因：把“手工看报告后改代码”升级为“系统自动发现问题并提出可验证的策略候选”，同时保持人类控制权。

受控边界：候选只能修改 Router Rule、Plan/Skill、参数提取、Reranker 权重、Answer/Verifier 规则等配置资产；不得自动修改 Python 源码、数据、测试断言、权限和发布门槛。

交付闭环：

- 代码：Feedback API、Observer、Bad-case Classifier、Candidate Proposer、隔离 Replay、审批状态机。
- 测试：反馈关联、归因、候选阈值、无回归门禁、未审批不可生效测试。
- 评测：每个候选全量运行四套评测和关联 bad cases，输出 baseline/candidate 差异。
- 文档：记录 Rule/Hook/Skill 模型、候选生命周期和安全边界。
- 演示：提交三条同类 wrong_tool 反馈，生成 Hook 候选，回放通过后进入 pending_review，但不自动发布。

发布门槛：candidate score 必须提升，regressed cases = 0，核心指标不下降，新增延迟 <= 15%，至少修复 2 个同类 bad cases。

预计工作量：5-7 天。

### Step 23：策略版本化、灰度、回滚与工程交付

当前问题：Router/Planner 规则仍固化在代码中，无法从某条 Trace 还原当时策略，也不能不改源码地激活或回滚策略。

新增原因：完成受控优化最后一段链路，使任何策略变化都可追踪、可审批、可灰度和可恢复。

交付闭环：

- 代码：Policy Repository/Engine、配置校验、activate/deprecate/rollback、稳定哈希灰度和回滚监控。
- 测试：版本切换、非法配置、灰度确定性、回滚、历史 Trace 策略关联测试。
- 评测：灰度组/对照组指标对比和自动回滚模拟。
- 文档：发布手册、回滚手册、Docker/CI 使用说明、最终架构文档。
- 演示：审批 policy_v2，20% 灰度；注入指标下降后自动切回 policy_v1。

验收门槛：任意 Trace 可定位策略版本；回滚不修改源码；CI 执行 Unit、Contract、Integration、Evaluation Smoke 和 Style/Type Check；Docker 可运行 CLI、API 与评测。

预计工作量：3-5 天。

## 5. 阶段优先级

| 优先级 | 范围 | 达成后的项目定位 |
|---|---|---|
| P0 | Step 17-19 | 证据可追溯、响应可校验的可信 Agent |
| P1 | Step 20-21 | 检索可量化、多轮可回放的工程 Agent |
| P2 | Step 22-23 | 具备受控自进化闭环的差异化 Agent 项目 |

若以近期面试为目标，先完成 P0，收益最高；如果时间充足，再完成 P1。P2 是项目最有区分度的部分，但必须建立在 P0/P1 的数据和验证能力上。

## 6. 统一 Definition of Done

以后每个 Step 均须满足：

- 代码已经接入主执行链，失败路径有明确状态，不存在只定义未调用的模块。
- 测试覆盖正常、边界、失败和回归；改变 Agent 行为时必须新增 Evaluation Case。
- 评测记录修改前后指标、修复 bad cases、新回归、延迟和工具调用次数。
- 文档同步更新架构、API Schema、配置、示例和评测结果。
- 新能力可通过一条命令或一个 API 请求演示。
- 实验记录只能追加，必须写清“当前问题、为什么添加、实现内容、影响、验证结果”。

## 7. 面试叙事升级路径

完成 Step 17-19 后可表述：

> 我把多工具 Agent 的工具输出统一为可追溯 Evidence，并在答案返回前增加确定性 Verifier，对版本、依赖方向、Citation 和混合任务完整性进行校验，同时设计 partial_success 语义，避免单个子任务缺数据导致整条任务被错误判定。

完成 Step 20-21 后可补充：

> 我将轻量检索升级为 BM25 与现有召回融合的 Hybrid RAG，用 Recall@K 和 MRR 验证提升；同时设计多轮 AgentContext 和可重放 Trace，使规划、工具、证据和校验结果能够统一关联。

完成 Step 22-23 后可补充：

> 我进一步实现了受控自进化闭环：系统从 Trace 和反馈中归因 bad case，生成配置型策略候选，经过全量 benchmark 回放和人工审批后灰度生效；出现指标回归时只切换策略版本即可回滚，不允许 Agent 自动修改源码或评测门槛。

## 8. 合规边界

本计划继续只使用公开风格或模拟数据，不引入、复制或还原任何企业内部数据。真实经历与个人复现项目继续分开表述：

- 真实经历：在网络设备研发环境中参与软件资产检索、解析自动化和 Agent 工具化探索。
- 个人复现：为验证 AI4SE Agent 方法论，基于模拟软件资产数据搭建并持续优化软件研发辅助 Agent 原型。
