# Step 23 Policy Rollout Evaluation

## Experiment

An approved Router Hook candidate was released as `policy_v2` at 20%. Assignment was sampled across 1,000 distinct sessions, then control and rollout behavior were compared. Finally, successful control samples and failed rollout samples were injected to exercise automatic rollback.

## Results

| Metric | Result |
|---|---:|
| Assignment samples | 1,000 |
| Rollout assignments | 184 |
| Observed rollout rate | 18.4% |
| Stable assignment for repeated session | 100% |
| Control Tool | `package_search` |
| Rollout Tool | `dependency_analysis` |
| Trace policy attribution | Passed |
| Automatic rollback | Passed |
| Restored policy | `deterministic-policy-v1` |
| Router/Planner/Workflow source hash unchanged | Passed |

All 12 policy gates passed. The observed 18.4% rate is inside the accepted 15-25% interval for a configured 20% rollout.

## Conclusion

Step 23 demonstrates a complete release control path: human-approved candidate, immutable policy version, deterministic gray assignment, trace-level attribution, metric-triggered rollback, and restoration without source modification.
