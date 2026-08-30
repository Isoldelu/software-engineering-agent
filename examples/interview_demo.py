"""Run a concise interview demo against a live Software-Agent API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_QUERY = "\u67e5\u4e00\u4e0b nginx \u7684\u7248\u672c\u53d8\u5316\u548c\u4f9d\u8d56"


def call_api(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    api_key: str | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - explicit local URL
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(
            f"Cannot reach {base_url}. Start uvicorn before running the demo: {exc.reason}"
        ) from exc


def compact_agent_result(result: dict[str, Any]) -> dict[str, Any]:
    verification = result.get("verification", {})
    return {
        "query": result.get("query"),
        "execution_status": result.get("execution_status"),
        "used_tools": result.get("used_tools", []),
        "tool_call_count": result.get("tool_call_count"),
        "evidence_count": result.get("evidence_count"),
        "citation_count": len(result.get("citations", [])),
        "verification_passed": verification.get("passed"),
        "trace_id": result.get("trace_id"),
        "answer": result.get("answer"),
    }


def compact_trace(trace: dict[str, Any]) -> dict[str, Any]:
    payload = trace.get("trace", trace)
    metrics = payload.get("metrics", {})
    return {
        "trace_schema_version": payload.get("trace_schema_version"),
        "trace_id": payload.get("trace_id"),
        "trace_complete": metrics.get("trace_complete"),
        "policy_version": payload.get("policy_version"),
        "step_count": len(payload.get("steps", [])),
        "total_latency_ms": metrics.get("total_latency_ms"),
    }


def compact_evaluation(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary", {})
    experiment = report.get("experiment", {})
    return {
        "suite_count": summary.get("suite_count"),
        "total_cases": summary.get("total_cases"),
        "total_bad_cases": summary.get("total_bad_cases"),
        "all_suites_passed": summary.get("all_suites_passed"),
        "agent_task_success": experiment.get("agent_task_success"),
        "routing_improvement": experiment.get("tool_accuracy_improvement"),
    }


def print_section(title: str, payload: dict[str, Any]) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--session-id", default="interview-demo")
    parser.add_argument("--skip-evaluation", action="store_true")
    parser.add_argument(
        "--api-key",
        default=os.getenv("SOFTWARE_AGENT_DEMO_API_KEY"),
        help="Optional API key; defaults to SOFTWARE_AGENT_DEMO_API_KEY.",
    )
    return parser


def configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        health = call_api(args.base_url, "/health", api_key=args.api_key)
        print_section("1. Service Health", health)

        result = call_api(
            args.base_url,
            "/agent/query",
            method="POST",
            payload={
                "query": args.query,
                "session_id": args.session_id,
                "persist_trajectory": False,
            },
            api_key=args.api_key,
        )
        print_section("2. Multi-Tool Agent", compact_agent_result(result))

        trace_id = result.get("trace_id")
        if trace_id:
            trace = call_api(args.base_url, f"/traces/{trace_id}", api_key=args.api_key)
            print_section("3. Replayable Trace", compact_trace(trace))

        if not args.skip_evaluation:
            report = call_api(
                args.base_url,
                "/evaluation/summary",
                api_key=args.api_key,
                timeout=180.0,
            )
            print_section("4. Frozen Evaluation", compact_evaluation(report))

        print("\nDemo completed. Browser: /demo | Evaluation: /evaluation-dashboard")
        return 0
    except RuntimeError as exc:
        print(f"demo failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
