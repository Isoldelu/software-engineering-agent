"""Show default offline planning and unavailable-online safe fallback."""

from __future__ import annotations

import json

from app.providers.service import run_agent_with_provider


for requested in ("offline", "openai"):
    result = run_agent_with_provider(
        "openssl 依赖哪些组件",
        provider=requested,
        allow_fallback=True,
        persist_trajectory=False,
    )
    print(json.dumps({
        "requested": requested,
        "selected_tool": result["selected_tool"],
        "effective_provider": result["provider"]["effective_provider"],
        "fallback_used": result["provider"]["fallback_used"],
        "usage": result["provider"]["usage"],
    }, ensure_ascii=False, indent=2))
