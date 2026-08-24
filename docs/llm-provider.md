# Optional LLM Provider And Dual Mode

## Purpose

Step 24 adds a real-provider integration boundary without making paid network access a runtime requirement. The default path remains deterministic and free.

```text
query -> PlannerGateway
      -> offline deterministic planner (default)
      -> OpenAI Responses structured plan (explicit opt-in)
      -> validate_plan()
      -> existing Tool / Evidence / Verifier / Trace workflow
```

The provider can only propose a plan. It cannot execute a Tool, modify Policy, bypass Evidence, disable the Verifier, or alter evaluation gates.

## Modes

| Requested mode | Requirement | Behavior |
|---|---|---|
| `offline` | None | Deterministic planner, zero network and zero tokens |
| `auto` | Environment configuration | Uses configured default, otherwise offline |
| `openai` | Explicit enable flag, API key, online dependency | Responses API structured plan |

Online plans use JSON Schema Structured Outputs and are validated again by the local `parse_llm_plan()` adapter. Unknown tools, malformed JSON, provider errors, and timeouts cannot reach the executor.

## Installation

Default runtime:

```bash
pip install -r requirements-runtime.txt
```

Optional online provider:

```bash
pip install -r requirements-online.txt
```

## Configuration

```text
SOFTWARE_AGENT_LLM_PROVIDER=offline|openai
SOFTWARE_AGENT_ENABLE_ONLINE_LLM=false|true
SOFTWARE_AGENT_OPENAI_MODEL=gpt-5-mini
SOFTWARE_AGENT_LLM_TIMEOUT=20
SOFTWARE_AGENT_LLM_MAX_OUTPUT_TOKENS=800
OPENAI_API_KEY=<secret>
```

Online access requires both `SOFTWARE_AGENT_ENABLE_ONLINE_LLM=true` and `OPENAI_API_KEY`. The key is read only by the SDK, and provider status reports only whether a key is configured. The key is not included in responses or Trace.

The default model is `gpt-5-mini`, which supports Responses and Structured Outputs according to the [official OpenAI model documentation](https://developers.openai.com/api/docs/models/gpt-5-mini). Override the model through configuration rather than source edits.

## Failure Behavior

With `allow_fallback=true`:

```text
missing key / disabled / timeout / API error / malformed plan / unknown tool
-> record normalized failure metadata
-> deterministic offline planner
-> normal Tool, Evidence, Verifier, Trace workflow
```

With `allow_fallback=false`, provider failure returns HTTP 503 and no Tool is executed.

## Cost Boundary

- Offline mode always reports zero token usage.
- Online calls are limited to one planning call per Agent request.
- `max_output_tokens` is clamped to 128-2,000 and timeout to 1-60 seconds.
- Responses use `store=false`.
- Usage and latency enter response/Trace for later cost and quality analysis.
- Step 24 evaluation uses Mock Online and makes zero paid API calls.

## Commands

```bash
python -B evaluation/provider_eval.py
python -B evaluation/eval_runner.py --suite provider
```

API:

```text
POST /agent/query-provider
GET  /providers/status
GET  /evaluation/provider
```
