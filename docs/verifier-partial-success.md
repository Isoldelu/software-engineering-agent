# Deterministic Verifier 与部分成功语义

## 1. 目的和意义

Step 18 解决了“事实来自哪里”，Step 19 进一步解决“返回前能否确认这些事实被正确使用”。

这一阶段的价值体现在四点：

1. 将错误发现前移。伪造版本、错误依赖方向和无效 Citation 不再等到离线评测才暴露，而是在 API 返回前被拦截。
2. 准确表达 Hybrid 执行结果。单个子任务缺数据时，系统返回 `partial_success`，不会把已经得到的可靠结果全部丢弃，也不会把整条任务伪装成完全成功。
3. 建立受控修复边界。系统只允许基于同一批 Tool Observation 重新组合一次答案，不重新规划、不重复调用 Tool，也不无限重试。
4. 为 Trace 和受控自进化提供监督信号。Verification Issue 可以直接进入后续 Bad-case 分类、反馈和策略回放。

## 2. 在线执行位置

```text
Plan
-> Tool Execution
-> Evidence/Citation
-> Draft Answer
-> Deterministic Verifier
-> optional one-time recomposition
-> Verification Result
-> API Response
```

Verifier 不调用外部 LLM，也不修改 Tool 结果、模拟数据或执行计划。

## 3. VerificationResult

```json
{
  "passed": true,
  "score": 1.0,
  "issues": [],
  "checked_rules": [
    "plan_complete",
    "claims_grounded",
    "citations_valid"
  ],
  "repair_count": 0,
  "initial_issues": []
}
```

Issue Schema：

```json
{
  "type": "unsupported_version_claim",
  "severity": "error",
  "message": "Version 9.9.9 is not present in Evidence.",
  "repairable": true,
  "rule": "version_claims_grounded"
}
```

## 4. 十一条确定性规则

| Rule | 检查内容 | 典型 Issue |
|---|---|---|
| `plan_complete` | 计划中的 Tool 是否实际执行 | `missing_tool` |
| `arguments_satisfied` | 每个步骤是否有可执行参数 | `missing_arguments` |
| `evidence_integrity` | success/not_found 与 Evidence 是否一致 | `missing_success_evidence` |
| `citations_valid` | Citation 是否引用当前 Evidence | `invalid_citation_reference` |
| `citation_coverage` | 所有 Evidence 是否都有 Citation | `missing_citation` |
| `version_claims_grounded` | 回答中的版本号是否存在于 Evidence | `unsupported_version_claim` |
| `dependency_direction_valid` | depends_on/required_by 方向是否正确 | `wrong_dependency_direction` |
| `execution_status_consistent` | 返回状态是否与 Tool 状态一致 | `execution_status_mismatch` |
| `not_found_semantics` | 无记录是否明确表达且无伪证据 | `not_found_has_evidence` |
| `hybrid_completeness` | Hybrid 是否说明失败或缺失子任务 | `answer_incomplete` |
| `answer_nonempty` | 最终回答是否为空 | `answer_empty` |

## 5. 四态执行语义

| Tool Observation 组合 | execution_status |
|---|---|
| 全部 `success` | `success` |
| `success` + `not_found/partial_success` | `partial_success` |
| 全部 `not_found` | `not_found` |
| 包含 `failed` 或无可用执行 | `failed` |

旧字段 `success: bool` 保持原义：只有所有 Observation 都是 `success` 时才为 `true`。因此旧调用方继续兼容，新调用方应优先读取 `execution_status`。

部分成功示例：

```text
PackageSearch(openssl) -> success
VersionCompare(nonexistent) -> not_found

execution_status = partial_success
success = false
answer = 已获得 openssl 包信息 + 明确说明缺失版本记录
```

## 6. 一次修复机制

```text
Draft Answer
-> Verify
-> 仅当所有 Issue 都可通过答案重组修复
-> 使用原 Observation 重新组合一次
-> Verify Again
-> Return
```

不可修复问题包括缺失 Tool、无效 Citation、Evidence Schema 错误和状态不一致。这些问题不能通过改写文字掩盖。

## 7. 评测

```bash
python -B evaluation/eval_runner.py --suite verifier
```

评测由两部分组成：

- 对 11 类故意构造的错误执行检测。
- 对原有 193 条合法请求计算 False Rejection。

当前结果：

```text
Injected error detection: 100%
False rejection rate: 0%
Partial-success classification: 100%
Invalid citation detection: 100%
Single deterministic repair: passed
Maximum repair count: 1
Bad cases: 0
```

## 8. 边界

- Verifier 是确定性规则系统，不声称具备通用自然语言事实核查能力。
- 当前版本重点验证结构化包、版本、依赖和 Citation 事实。
- 评测使用模拟数据和注入错误，不代表真实生产流量效果。
- Step 21 将把 VerificationResult 与 trace_id、session_id 和策略版本进一步关联。
