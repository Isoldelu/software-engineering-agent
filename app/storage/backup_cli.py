"""CLI for logical backup verification and restore."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.storage.backup import ControlPlaneBackupService
from app.storage.database import build_store_from_env


def main() -> int:
    parser = argparse.ArgumentParser(description="Control-plane logical backup utility.")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--create", type=Path)
    actions.add_argument("--verify", type=Path)
    actions.add_argument("--restore", type=Path)
    parser.add_argument("--namespace", action="append", dest="namespaces")
    parser.add_argument("--clear-existing", action="store_true")
    args = parser.parse_args()
    store = build_store_from_env()
    if store is None:
        raise RuntimeError("SOFTWARE_AGENT_DATABASE_URL is required.")
    service = ControlPlaneBackupService(store)
    try:
        if args.create:
            report = service.create(args.create, namespaces=args.namespaces)
        elif args.verify:
            report = service.verify(args.verify)
        else:
            report = service.restore(args.restore, clear_existing=args.clear_existing)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
