"""Entry point for the AI4SE Software Agent demo."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.agent.workflow import run_agent


def main() -> None:
    args = sys.argv[1:]
    llm_plan_output = None
    if "--llm-plan" in args:
        index = args.index("--llm-plan")
        plan_path = Path(args[index + 1])
        llm_plan_output = plan_path.read_text(encoding="utf-8")
        del args[index:index + 2]

    query = " ".join(args).strip() or "query openssl version"
    result = run_agent(query, persist_trajectory=True, llm_plan_output=llm_plan_output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
