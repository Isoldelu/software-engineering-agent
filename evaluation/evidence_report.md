# Step 18 Evidence/Citation Evaluation Report

## Scope

The evaluation replays all 193 existing cases across standard, challenge, robustness, and large benchmark datasets. It does not add duplicate cases to the main 193-case total.

## Results

| Metric | Result | Target |
|---|---:|---:|
| Citation coverage | 100% | >= 95% |
| Evidence normalization success | 100% | 100% |
| Citation correctness | 100% | >= 95% |
| not_found without Citation | 100% | 100% |
| Unsupported structured facts | 0 | 0 |
| Bad cases | 0 | 0 |

## Evaluation Bug Found

The first implementation counted not-found cases as covered in the Citation numerator while excluding them from the denominator. This produced an impossible coverage value of 101.58%.

The metric was corrected to count only cases where a Citation is required in both numerator and denominator. The corrected Citation coverage is 100%.

## Reproduce

```bash
python -B evaluation/eval_runner.py --suite evidence
python -B -m pytest -q tests/test_evidence.py -p no:cacheprovider
```

## Interpretation Boundary

These results validate deterministic Evidence construction and Citation integrity on simulated data. They do not measure citation quality from a nondeterministic external LLM.
