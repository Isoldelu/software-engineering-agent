# Step 14 Robustness Evaluation Report

## Current Problem

The existing benchmark and challenge suites mainly use standard queries such as:

```text
openssl dependencies
1214 release packages and their dependencies
which package owns libpcap.so
```

These cases prove that the Agent can handle normalized inputs, but they do not fully test real engineering-style questions. In real usage, developers often ask with aliases, shorthand, mixed intent, or missing-data requests.

## Why This Step Was Added

This step adds a harder robustness suite to verify whether the Agent still works when the query is less standardized:

- Domain aliases: `安全通信库` -> `openssl`
- Tool aliases: `抓包工具` -> `tcpdump`
- Functional aliases: `网口诊断工具` -> `ethtool`
- Reverse dependency: `libpcap.so 是谁依赖引入的`
- Multi-intent query: `查一下 nginx 的版本变化和依赖`
- Missing release query: `1216 发布里新增了什么`

This makes the project closer to an AI4SE Agent demo instead of a fixed-template QA script.

## Implementation

Files changed:

- `evaluation/robustness_cases.json`
- `evaluation/eval_runner.py`
- `app/agent/router.py`
- `app/agent/planner.py`
- `app/agent/workflow.py`
- `app/tools/dependency_tool.py`
- `app/tools/rag_tool.py`
- `app/api/server.py`

Key changes:

- Added a new `Software-Agent-Robustness` suite.
- Added package alias mapping in Router.
- Added reverse dependency lookup in `DependencyAnalysisTool`.
- Added hybrid package dependency + version planning.
- Passed normalized package arguments from Planner to tool execution.
- Added exact release filtering in RAG retrieval to reduce false positives.
- Added `GET /evaluation/robustness`.

## Verified Result

```text
Software-Agent-Robustness:
total: 6
tool_routing_accuracy: 1.0
task_success_rate: 1.0
answer_grounding_accuracy: 1.0
answer_accuracy: 1.0
average_tool_calls: 1.6667
bad_cases: []
```

Full suite after Step 14:

```text
Software-Agent-Bench: all metrics 1.0
Software-Agent-Challenge: all metrics 1.0
Software-Agent-Robustness: all metrics 1.0
```

## Impact

After this step, the Agent can handle more realistic engineering queries:

```text
安全通信库依赖什么？
-> openssl depends on: libssl.so, libcrypto.so.

libpcap.so 是谁依赖引入的？
-> libpcap.so is required by: tcpdump.

查一下 nginx 的版本变化和依赖
-> package_search -> dependency_analysis -> version_compare
```

Interview framing:

> I added a robustness evaluation suite beyond the standard benchmark. It covers alias-based queries, reverse dependency questions, mixed-intent planning, and missing-release retrieval. This helped expose whether the Agent was only matching fixed templates or could handle more realistic software engineering expressions.

