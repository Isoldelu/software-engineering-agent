# Step 19 Verifier and Partial-success Evaluation Report

## Results

| Metric | Result | Target |
|---|---:|---:|
| Injected error detection | 100% | >= 95% |
| False rejection rate | 0% | <= 5% |
| Partial-success classification | 100% | >= 95% |
| Invalid Citation detection | 100% | 100% |
| Maximum repair count | 1 | 1 |
| Verifier bad cases | 0 | 0 |

## Injected Errors

The challenge set covers fabricated versions, reversed dependency direction, invalid and missing Citations, missing Tool execution, incorrect execution status, empty answers, not-found responses with fabricated Evidence, incomplete Hybrid answers, missing arguments, and successful observations without Evidence.

## Bad Cases Found During Development

1. Shared-library suffix parsing initially treated the period in `.so` as a sentence delimiter. Valid dependencies such as `libpcap.so` were truncated and falsely rejected. The parser now separates sentence punctuation from component extensions.
2. The first missing-step mutation removed only one expanded `version_compare` call. Because another call of the same Tool remained, `plan_complete` correctly considered the Tool executed. The injection now removes every observation produced by the target plan step.

## Reproduce

```bash
python -B evaluation/eval_runner.py --suite verifier
python -B -m pytest -q tests/test_verifier.py -p no:cacheprovider
```

## Interpretation Boundary

The Verifier is deterministic and domain-specific. Results measure the current simulated software-asset workload and injected errors, not open-domain fact checking.
