# 2-3 Minute Interview Demo Runbook

## Demo Goal

Use one compound engineering query to show planning, multi-tool execution, grounded evidence,
verification, replayable Trace, evaluation, and deployability without relying on a paid API.

## Preflight

```powershell
python -m pip install -r requirements-dev.txt
uvicorn app.api.server:app --host 127.0.0.1 --port 8000
```

Open these tabs before the interview:

- `http://127.0.0.1:8000/demo`
- `http://127.0.0.1:8000/evaluation-dashboard`
- `https://github.com/Isoldelu/software-engineering-agent/actions/runs/32742656550`

Optional command-line preflight:

```powershell
python examples/interview_demo.py --skip-evaluation
```

Remove `--skip-evaluation` when you want the script to execute the frozen evaluation summary.

## Timeline

### 0:00-0:25: Positioning

Say:

> 这是一个基于模拟软件资产数据复现方法论的 AI4SE Agent。它不是普通 RAG，而是让
> Planner 根据任务选择结构化工具或文档检索，再通过 Evidence、Verifier 和 Trace 形成
> 可验证、可回放、可评测的执行链。

### 0:25-1:15: Compound Query

Submit:

```text
查一下 nginx 的版本变化和依赖
```

Point to these fields in order:

1. `used_tools`: package, dependency, and version tools are composed by the planner.
2. `plan`: the system exposes its execution order instead of hiding it in free-form text.
3. `evidence_items` and `citations`: each fact is tied to a simulated source record.
4. `verification`: the final answer is checked before being marked successful.
5. `trace_id`: the exact execution can be inspected and replayed.

### 1:15-1:55: Evaluation

Open the Evaluation Dashboard and say:

> 我没有只展示几个成功样例，而是冻结了 193 条用例，并比较 DirectLLMProxy、RAGOnlyProxy
> 和 Agent。这里的 Proxy 是离线可复现实验，不冒充真实大模型效果。

Show:

- 193 total cases and zero current bad cases.
- 61.76% to 100% routing optimization result.
- DirectLLMProxy 22.94%, RAGOnlyProxy 57.06%, Agent 100% task success.

### 1:55-2:30: Controlled Optimization

Say:

> Trace 和用户反馈会进入受控 Bad-case Loop。系统只能生成白名单内的配置候选，必须经过
> 193 条回放、Shadow Evaluation 和人工审核；策略发布使用稳定灰度分流并支持自动回滚，
> Agent 不能自行修改源码或跳过门禁。

### 2:30-3:00: Engineering Evidence And Boundary

Open the green Actions Run and say:

> 真实 PostgreSQL CI 中两个 Worker 完成 100 次请求，杀掉一个 Worker 后替换进程完成 40 次
> 恢复请求，均无 5xx；数据库停机时 readiness 从 200 降为 503，恢复后回到 200。所有数据
> 都是模拟数据，真实 Provider A/B 因没有明确预算暂未执行。

## Backup Queries

| Purpose | Query |
|---|---|
| Package lookup | `查询 openssl 1213 版本` |
| Reverse dependency | `哪些包依赖 libssl.so` |
| Hybrid release task | `1214 release packages and their dependencies` |
| Multi-turn context | First `查询 nginx`, then `它有哪些依赖` with the same session |
| No-answer behavior | `查询不存在的 package-not-found` |

## Failure Fallback

- If port 8000 is occupied, start Uvicorn on 8010 and pass
  `--base-url http://127.0.0.1:8010` to the script.
- If the live evaluation is slow, use `--skip-evaluation` and show the retained v1.0.0 Evidence
  plus the green Actions Run.
- If the browser cannot open, run `python examples/interview_demo.py`; its output contains the
  tool chain, evidence count, verification state, Trace ID, and optional evaluation summary.
- Do not switch to a real Provider during an interview unless credentials and budget have already
  been tested. The deterministic mode is the intended reliable demo path.

## Close

End with the engineering lesson:

> 这个项目的重点不是把 LLM 接到搜索框，而是把工具选择、事实证据、失败语义、执行轨迹、
> 优化候选和策略发布都变成可测试的工程契约。

