# Policy Versioning And Rollout

## Purpose

Step 23 turns an approved Step 22 configuration candidate into a controlled runtime policy. A release no longer requires editing Router or Workflow source code.

## Lifecycle

```text
approved candidate
-> policy_vN draft
-> deterministic rollout (1-100%)
-> promote to stable OR rollback to parent
-> deprecate when no longer needed
```

The initial stable policy is `deterministic-policy-v1`. New versions keep their parent policy, source candidate, creator, timestamps, configuration, rollout percentage, and status.

## Assignment

Assignments use a SHA-256 bucket derived from `session_id`. The same session always receives the same cohort while a rollout configuration is unchanged.

```text
bucket < rollout_percentage -> rollout policy
otherwise                   -> stable control policy
```

The selected `policy_version` and full `policy_assignment` are written to the Agent response and `trace-v1`, so historical execution remains attributable after promotion or rollback.

## Safety Gates

- Only a Step 22 candidate in `approved` state can create a policy.
- Candidate and policy schemas are validated again at release time.
- Policy rules can only select registered Agent tools and supported match modes.
- One rollout policy can be active at a time.
- Stable policy remains the control until explicit promotion.
- Rollback changes repository state; it does not edit Python source.
- Policy state is persisted to `data/policy_state.json` in the default service.

Set `SOFTWARE_AGENT_POLICY_STATE_PATH` before process startup to place the state file on an external volume or another writable location. The Docker Compose default continues to use the mounted `/app/data` directory.

## Monitoring

The monitor tracks success rate, failure count, average latency, and sample count for control and rollout. After at least five samples per cohort, it automatically rolls back when rollout success is below `80%` or trails control by more than `10` percentage points.

See `docs/release-runbook.md` and `docs/rollback-runbook.md` for operations.
