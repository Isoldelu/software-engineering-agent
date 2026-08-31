# Reviewed Evolution-to-Policy Bridge Report

## Result

```text
Candidate types: 3
Policy versions created: 3
Immutable bridge records: 3
Idempotent replays: 3/3
Rollback: policy_v4 -> policy_v3
Paid API calls: 0
Result: passed
```

## Gates

| Gate | Result |
|---|---:|
| Approved candidate required | passed |
| Shadow pass required | passed |
| Three supported assets translated | passed |
| Candidate and config digests retained | passed |
| One Policy per Candidate | passed |
| Duplicate requests idempotent | passed |
| Reviewed assets accumulate in stable config | passed |
| Rollback restores parent Policy | passed |
| Rollback deactivates source Candidate | passed |
| Automatic activation remains blocked | passed |

This suite consumes deterministic snapshots of the three Step 25 reviewed candidate types. Step 25 separately owns the expensive 193-case/30-case Shadow and regression proof; Step 33 evaluates the release boundary without duplicating that computation.

Run:

```bash
python -B evaluation/evolution_bridge_eval.py
python -B evaluation/eval_runner.py --suite evolution-bridge
```
