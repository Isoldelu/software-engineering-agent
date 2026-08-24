# Policy Rollback Runbook

## Automatic Rollback

The monitor evaluates control and rollout after each sample. It rolls the rollout policy back to its parent when minimum sample requirements are met and either gate fails:

- rollout success rate is below `80%`; or
- rollout success rate is more than `10` percentage points below control.

The rollback event records reason, metrics, source policy, restored policy, and timestamp. The source candidate is deactivated.

## Manual Rollback

```bash
curl -X POST http://127.0.0.1:8000/policies/policy_vN/rollback \
  -H "Content-Type: application/json" \
  -d '{"reason":"operator incident reference"}'
```

## Verification

1. `GET /policies` reports no rollout policy and the expected stable parent.
2. New assignments resolve to the restored stable policy.
3. Existing traces still identify the historical rollout policy.
4. Candidate `active` is false and its activation status records rollback.
5. Run `python -B evaluation/policy_eval.py` and `python -B evaluation/baseline.py --check`.

Rollback is repository state transition only. Do not edit Router/Planner/Workflow source to perform or conceal a rollback.
