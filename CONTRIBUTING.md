# Contributing

## Development Setup

```bash
python -m venv .venv
python -m pip install -r requirements-dev.txt
python -B -m pytest -q -p no:cacheprovider
python -B evaluation/baseline.py --check
```

## Change Requirements

- Keep all datasets public-style or simulated. Never submit employer or customer data.
- Preserve the V1 API and frozen 193-case compatibility baseline unless a versioned contract change is intentional.
- Add focused tests for behavior changes and update the relevant evaluation report.
- Do not weaken human review, policy rollout, authorization, Evidence, or Verifier gates to make a test pass.
- Do not commit `.env`, API Keys, database credentials, Trajectories, Audit logs, backups, or generated artifacts.
- Append experiments to `实验记录.md`; do not overwrite earlier records.

## Pull Requests

Use a focused branch and complete the pull request template. CI must pass unit/contract tests, frozen baseline checks, Docker build, and PostgreSQL integration before merge.
