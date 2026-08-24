"""CLI entry point for scheduled bounded retention."""

from __future__ import annotations

import argparse
import json

from app.maintenance.retention import RetentionService
from app.storage.database import build_store_from_env


def main() -> int:
    parser = argparse.ArgumentParser(description="Run control-plane retention.")
    parser.add_argument("--apply", action="store_true", help="Delete eligible records.")
    parser.add_argument("--batch-limit", type=int, default=1000)
    args = parser.parse_args()
    store = build_store_from_env()
    if store is None:
        raise RuntimeError("SOFTWARE_AGENT_DATABASE_URL is required for retention.")
    report = RetentionService(store).run(
        dry_run=not args.apply,
        batch_limit=args.batch_limit,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
