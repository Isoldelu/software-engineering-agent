# Policy Release Runbook

## Preconditions

1. Candidate status is `approved` after linked replay and the frozen 193-case regression gate.
2. Candidate is inactive and contains only allowed configuration changes.
3. API health endpoint returns `ok`.

## Release At 20%

```bash
curl -X POST http://127.0.0.1:8000/policies/from-candidate/CANDIDATE_ID \
  -H "Content-Type: application/json" \
  -d '{"rollout_percentage":20,"released_by":"reviewer-name"}'
```

Inspect state and deterministic assignment:

```bash
curl http://127.0.0.1:8000/policies
curl http://127.0.0.1:8000/policies/assignment/session-001
```

Confirm that rollout traces contain `policy_version=policy_vN`, `cohort=rollout`, and expected Tool selection. Control traces must continue to use the stable parent policy.

## Change Percentage

```bash
curl -X POST http://127.0.0.1:8000/policies/policy_vN/rollout \
  -H "Content-Type: application/json" \
  -d '{"rollout_percentage":50}'
```

## Promote

Promote only after evaluation and live monitor gates remain healthy:

```bash
curl -X POST http://127.0.0.1:8000/policies/policy_vN/promote
```

Record the policy ID, candidate ID, reviewer, metrics, and promotion time in the release ticket.
