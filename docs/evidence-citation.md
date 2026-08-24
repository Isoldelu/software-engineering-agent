# Evidence 与 Citation 事实证据层

## 1. 目标

Step 18 将原来的“证据来源路径”扩展为可定位到具体记录或文档 Chunk 的结构化 Evidence，并通过 Citation 将最终答案与 Evidence 建立引用关系。

设计原则：

- 保留 V1 的 `evidence` 路径字段，确保旧调用方兼容。
- 新增 `evidence_items`，不复用旧字段表达新语义。
- Evidence ID 由来源类型、来源 ID、内容和 Tool 名称确定性生成。
- `not_found` 可以说明查询过哪些数据源，但不能生成事实 Evidence 或 Citation。
- Hybrid Plan 合并多个 Tool 的 Evidence，并按 ID 去重。
- 当前 Citation 作为独立结构化字段返回，不把引用标记拼接到答案文本中。

## 2. Evidence Schema

```json
{
  "evidence_id": "ev_837f01add1973bb51478",
  "source_type": "package_record",
  "source_id": "packages.json#package=openssl;release=1213;architecture=arm64",
  "title": "Package openssl 3.0.8",
  "content": "{...}",
  "tool_name": "package_search",
  "confidence": 1.0,
  "metadata": {
    "package": "openssl",
    "release": "1213",
    "architecture": "arm64"
  }
}
```

`evidence_id` 使用 SHA-256 派生并截取 20 个十六进制字符。相同来源事实在重复执行中生成相同 ID，不依赖执行时间或本机绝对路径。

## 3. Citation Schema

```json
{
  "evidence_id": "ev_837f01add1973bb51478",
  "title": "Package openssl 3.0.8",
  "source_type": "package_record",
  "snippet": "{...}"
}
```

Citation 只引用当前响应中的 Evidence。`EvidenceValidator` 会拒绝不存在的 Evidence ID 和重复/缺失 Evidence ID。

## 4. ToolObservation V2

五个 Tool 保留原有顶层字段，同时增加统一的 `normalized_observation`：

```json
{
  "status": "success",
  "result": {},
  "evidence": [],
  "error": null,
  "metadata": {
    "latency_ms": 0.123,
    "evidence_normalized": true,
    "evidence_count": 1,
    "observation_schema_version": "tool-observation-v2"
  }
}
```

状态集合固定为 `success`、`partial_success`、`not_found` 和 `failed`。Step 19 已完成 Workflow 级四态聚合，并通过 `execution_status` 对外返回。

## 5. Tool 来源映射

| Tool | source_type | source_id 粒度 |
|---|---|---|
| PackageSearchTool | `package_record` | package + release + architecture |
| DependencyAnalysisTool | `dependency_record` / `dependency_edge` | package 记录或具体依赖边 |
| VersionCompareTool | `version_record` | package + old/new version |
| ComponentMappingTool | `component_mapping` | component + owner package + release |
| RAGRetrieverTool | `document_chunk` | source + title + content hash |

## 6. Workflow 聚合

```text
Tool legacy output
-> EvidenceNormalizer
-> normalized_observation
-> Workflow merge by evidence_id
-> Citation generation
-> API response / trajectory / memory
```

API 新增 `evidence_items`、`citations` 和 `evidence_count`。

## 7. 兼容策略

- 旧 `evidence: list[str]` 和 Tool 业务字段保持不变。
- `/agent/query` 原有 11 个字段保持不变。
- Step 17 baseline-v1 使用递归兼容比较：旧键和值必须完全一致，允许新增字段。
- Golden Workflow 同样校验旧输出是新输出的兼容子集。

## 8. 评测方法

```bash
python -B evaluation/eval_runner.py --suite evidence
```

当前结果：

```text
cases: 193
citation_coverage: 100%
evidence_normalization_success: 100%
citation_correctness: 100%
not_found_without_citation: 100%
unsupported_structured_facts: 0
bad_cases: 0
```

该结果基于模拟数据和离线确定性评测，不代表外部 LLM 或真实企业数据效果。
