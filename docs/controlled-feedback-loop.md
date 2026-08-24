# Step 22: Controlled Feedback And Bad-case Loop

## Purpose

Step 22 turns Trace-linked user feedback into a configuration-only policy candidate. The loop can discover, classify, propose, replay, and review an optimization, but it cannot modify source code or activate a policy.

```text
trace-v1
-> Feedback Observer
-> Bad-case Classifier
-> group at least 3 matching records
-> configuration-only Candidate Proposer
-> linked bad-case replay
-> frozen 193-case regression
-> safety and metric gates
-> pending_review
-> human approve/reject
-> approved but inactive
```

## Demonstrated Bad Case

The current Router does not recognize `prerequisites` as dependency intent:

```text
openssl prerequisites -> package_search (wrong)
nginx prerequisites   -> package_search (wrong)
tcpdump prerequisites -> package_search (wrong)
```

Three Trace-linked negative feedback records produce this candidate asset:

```json
{
  "asset_type": "router_hook",
  "config": {
    "rules": [{
      "match": {"terms": ["prerequisites"], "mode": "any"},
      "action": {
        "intent": "dependency_analysis",
        "tool": "dependency_analysis"
      },
      "priority": 100
    }]
  }
}
```

This configuration is evaluated in an isolated runner and is never injected into the live Agent.

## Feedback Schema

Each Feedback record contains:

```text
feedback_id / trace_id / rating / comment
issue_type / expected_tool / fingerprint / status
observed query, selected tool, policy version, execution status,
Verification summary and Evidence IDs
```

Supported attribution types are `wrong_tool`, `tool_execution_failed`, `answer_not_grounded`, `answer_incomplete`, and `verification_failed`. The current automatic proposer intentionally supports only grouped `wrong_tool` Router Hooks.

## Candidate Lifecycle

```text
draft -> replaying -> pending_review -> approved
                   -> rejected
```

- At least 3 matching negative records are required.
- Only a `pending_review` candidate may be reviewed.
- Human approval records reviewer, note, and timestamp.
- `approved` does not mean active.
- `/activate` is explicitly blocked until Step 23 provides policy versioning, rollout, and rollback.

## Safety Scope

The validator rejects candidates that attempt to change:

- Python source
- datasets
- test assertions
- permissions
- release gates

Step 22 accepts only a structured Router Hook with known tools, deterministic terms, and a declared forbidden-change scope.

## Regression Gates

A candidate reaches `pending_review` only when all gates pass:

1. Configuration scope is valid.
2. Linked candidate score is higher than baseline.
3. At least 2 related bad cases are fixed.
4. Regressed cases across the frozen 193-case suite equal 0.
5. Routing, task success, grounding, and answer accuracy do not decrease.
6. Added Agent latency is no more than 15%.

## API

```text
POST /feedback
GET  /feedback
POST /candidates/propose
GET  /candidates
GET  /candidates/{candidate_id}
POST /candidates/{candidate_id}/evaluate
POST /candidates/{candidate_id}/review
POST /candidates/{candidate_id}/activate  # blocked in Step 22
GET  /evaluation/feedback
```

## Evaluation Results

| Metric | Result |
|---|---:|
| Feedback/Trace linkage | 100% |
| Classification accuracy | 100% |
| Linked routing score | 0% -> 100% |
| Fixed bad cases | 3 |
| Frozen regression cases | 193 |
| Regressed cases | 0 |
| Core metric decrease | 0 |
| Added latency | 0% measured increase |
| Final candidate state | `pending_review`, inactive |

The evaluation uses only simulated software data and deterministic local execution.
