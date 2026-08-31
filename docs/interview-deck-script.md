# Software Engineering Agent 面试 Deck 讲稿

配套文件：[Software-Agent-Interview-Deck.pptx](Software-Agent-Interview-Deck.pptx)

> 版本说明：该 Deck 固定为 Step 34 的 155-tests / zero-paid-call 历史快照。Step 35 的当前补充证据为 160 tests、GitHub Actions Run `33375239707` 和 20-case Real DeepSeek JSON Planner A/B；讲解新结果时应同时打开 [`real-deepseek-provider-ab.md`](real-deepseek-provider-ab.md)，不要直接把旧页数字读成当前数字。

建议总时长：3-4 分钟。现场优先讲结论，不逐字朗读页面。

## 第 1 页：项目定位

> 这是我基于公开风格模拟数据完成的个人复现项目，不包含华为内部数据。项目面向软件研发资产查询与分析，通过 Agent 组合结构化工具和 RAG，并把每次执行转化为可验证、可回放、可评测的 Trace。该 Deck 对应 Step 34 快照，当时通过 155 项自动化测试和 193 条冻结评测，尚未执行真实 Provider A/B。

## 第 2 页：系统架构

> 用户 Query 先进入多轮 Context，再由 Planner 和 Router 决定单工具或 Hybrid Plan。五个工具分别处理 Package、Dependency、Version、Component 和 RAG 检索。工具结果不会直接拼成答案，而是统一生成 Evidence 和 Citation，再由确定性 Verifier 判断成功、部分成功或失败。Trace 会进入评测和受控优化闭环，候选策略必须经过 Shadow、全量回归、人工审核、灰度和回滚。

## 第 3 页：复合任务 Demo

> 以“查一下 nginx 的版本变化和依赖”为例，Planner 组合了 Package Search、Dependency Analysis 和 Version Compare。页面中可以看到 3 条 Evidence、3 条 Citation、Verifier 通过以及完整 Trace。这里要强调，多工具规划不是为了增加调用次数，而是让复合问题被拆成可验证的子任务。

## 第 4 页：评测与优化

> 项目建立了任务成功率、路由准确率、答案正确性和调用效率等指标。早期关键词 Router 在挑战集上只有 61.76%，加入别名映射、工具描述、Hybrid Planner 和 Bad-case 回归后达到冻结集 100%。DirectLLMProxy 的 22.94% 和 RAGOnlyProxy 的 57.06% 都是离线可复现基线，不代表真实商业模型 A/B，这个边界我会明确说明。

## 第 5 页：工程交付与边界

> 当前 GitHub Actions Run `33363220127` 同时验证了 155 项测试、Docker 构建和 PostgreSQL 多 Worker 路径。PostgreSQL Bridge 故障注入通过 16/16 Gate，真实双 Worker 并发发布通过 14/14 Gate，并保留独立 Artifact。受控自进化通过 Reviewed Bridge 连接人审候选与灰度策略，但不会自动修改源码或自行发布。下一项独立实验是小预算真实 Provider A/B，需要显式 API Key、预算上限和成本记录。

## 追问转场

- 问“为什么不是普通 RAG”：回到第 2 页，强调规划、工具、证据、Verifier、Trace 和策略闭环。
- 问“100% 是否可信”：回到第 4 页，限定为模拟数据上的冻结评测集，并说明 Challenge Set 和 Bad-case 回归。
- 问“自进化做了什么”：回到第 2、5 页，说明离线挖掘、配置候选、Shadow、全量回归、人审、灰度与回滚。
- 问“是否使用华为数据”：回到第 1、5 页，明确个人复现只使用公开风格模拟数据。
- 问“是否真实上线”：说明已完成服务化、容器、数据库、鉴权、审计和 CI 门禁，但没有宣称生产 SLA。
