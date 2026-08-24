# Step 12 Bad Case Optimization Report

## Goal

Build a repeatable bad-case loop for the Software Engineering Agent:

```text
Challenge Cases -> Evaluation -> Failure Taxonomy -> Targeted Fix -> Re-evaluation
```

This keeps the main benchmark stable while using harder cases to drive the next optimization round.

## Added Challenge Suite

File: `evaluation/challenge_cases.json`

The challenge suite contains 5 difficult cases:

- Unknown release dependency query: `1215 release packages and their dependencies`
- Unknown component ownership query: `which package owns legacycrypto.so`
- Missing version record query: `compare ethtool version changes`
- Hybrid document + package + dependency query: `according to release note, what dependencies do openssl have in 1213`
- Hybrid release + package + version query: `1214 release packages and their version changes`

## Initial Finding

Before optimization, the release version query was routed to a single `version_compare` call:

```text
Query:
1214 release packages and their version changes

Actual tools:
version_compare

Expected tools:
rag_retrieval -> package_search -> version_compare -> version_compare

Reason:
wrong_tool
```

## Optimization Applied

Files changed:

- `app/agent/planner.py`
- `app/agent/workflow.py`
- `evaluation/eval_runner.py`

Implementation:

- Added `hybrid_release_version_compare` planning logic.
- Added a hybrid plan for `release + version changes` tasks:

```text
rag_retrieval -> package_search -> version_compare
```

- Extended the workflow executor so `version_compare` can consume packages found by `package_search`.
- Extended hybrid answer generation to include version-change summaries.
- Fixed bad-case detection so `answer_missing_expected_content` is also counted as a bad case.
- Added failure taxonomy and optimization suggestions to the evaluation report.

## Re-evaluation Result

Main benchmark:

```text
total: 12
tool_routing_accuracy: 1.0
task_success_rate: 1.0
answer_grounding_accuracy: 1.0
answer_accuracy: 1.0
average_tool_calls: 1.4167
bad_cases: []
```

Challenge suite after optimization:

```text
total: 5
tool_routing_accuracy: 1.0
task_success_rate: 0.2
answer_grounding_accuracy: 0.2
answer_accuracy: 0.6
average_tool_calls: 2.4
bad_case_types:
  tool_execution_failed: 4
```

The previous `wrong_tool` bad case was fixed. The remaining bad cases are now mainly knowledge coverage gaps:

- Release `1215` does not exist in simulated package/release data.
- `legacycrypto.so` does not exist in simulated package file lists.
- `ethtool` has no version-change record.
- `tcpdump` has no version-change record, so the release-level version comparison is only partially answered.

## Next Optimization Direction

Recommended next round:

- Add explicit `not_found` answer quality rules so missing-data answers can still be evaluated as valid when the expected behavior is "no record found".
- Expand `versions.json` with `ethtool` and `tcpdump` change records.
- Add a partial-success status for hybrid plans so one missing package record does not make the whole plan fail.
- Add more ambiguous natural-language queries to test Router robustness.

## Step 13 Follow-up

Goal:

Convert the remaining `tool_execution_failed` cases into either valid `not_found` behavior or fully covered knowledge-base answers.

Changes:

- Added version records for `ethtool` and `tcpdump` in `data/versions.json`.
- Added a clearer missing-release message in `PackageSearchTool`.
- Added missing-record summaries to hybrid answers.
- Added `expected_status` support in `evaluation/eval_runner.py`.
- Marked unknown release/component cases as expected `not_found` in `evaluation/challenge_cases.json`.

Result:

```text
benchmark:
  total: 12
  tool_routing_accuracy: 1.0
  task_success_rate: 1.0
  answer_grounding_accuracy: 1.0
  answer_accuracy: 1.0
  bad_cases: []

challenge:
  total: 5
  tool_routing_accuracy: 1.0
  task_success_rate: 1.0
  answer_grounding_accuracy: 1.0
  answer_accuracy: 1.0
  bad_cases: []
```

Current conclusion:

The first challenge suite has been closed. The next optimization round should add a harder challenge set with ambiguous package names, noisy release-note wording, multi-hop dependency questions, and expected partial-success cases.
