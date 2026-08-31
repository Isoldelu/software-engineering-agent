# Real DeepSeek Provider A/B

## Goal

This experiment validates a real LLM Planner without replacing the deterministic Tool executor. DeepSeek produces a JSON plan; the existing local parser, Tool allowlist, argument validator, Workflow, Evidence, Verifier, and fallback remain authoritative.

## Security And Budget Controls

- `DEEPSEEK_API_KEY` is read from the process environment only.
- The Key is never written to source, `.env`, Trace, Audit, reports, or Git history.
- Online access remains disabled by default.
- The runner requires `--confirm-paid-calls` and caps one run at 20 requests.
- Non-thinking mode and bounded output tokens are used for Planner tasks.
- Reports retain Query, selected tools, latency, token usage, fallback type, and estimated cost only.

## Architecture

```text
Query
-> DeepSeek V4 Flash JSON Planner
-> parse_llm_plan()
-> local schema and Tool allowlist validation
-> deterministic Workflow and Tools
-> Evidence / Verifier / Trace
-> deterministic fallback on Provider or schema failure
```

The adapter uses DeepSeek's OpenAI-compatible `/chat/completions` endpoint with `response_format={"type":"json_object"}` and `thinking.type=disabled`. JSON validity alone is insufficient: local validation still rejects unknown Tools and non-object arguments.

## Initial Diagnostic

The first real response was valid JSON but failed the local contract because `arguments` was a string and the model added a speculative Tool. The Agent safely fell back to deterministic planning. A diagnostic call confirmed `step_1_arguments_must_be_object` rather than weakening the validator.

The Prompt contract was then tightened:

- every `arguments` value must be a JSON object;
- single-intent queries use one minimal Tool;
- `hybrid_plan` is reserved for explicit multi-intent work;
- release package fan-out uses `from_previous_packages=true`;
- release-note/manual wording controls whether RAG is required.

## Real Results

| Metric | Before Prompt/Fan-out Optimization | After Optimization |
|---|---:|---:|
| Cases | 20 | 20 |
| Structured Plan valid rate | 100% | 100% |
| Exact plan parity vs deterministic | 60% | 65% |
| Required Tool accuracy | not labeled in raw Before run | 100% |
| Strict task success | 85% | 95% |
| Fallback rate | 0% | 0% |
| P50 latency | 1,615.805 ms | 1,627.642 ms |
| P95 latency | 1,967.161 ms | 2,276.123 ms |
| Total tokens | 18,304 | 19,628 |
| Peak-price cost upper bound | $0.01103432 | $0.01172600 |

The remaining strict failure is the intentionally missing `1215` release. The raw After report conservatively counts `success=false`; future runs use an explicit `expected_status=not_found` label so correct no-answer behavior is not confused with execution failure.

Across connectivity, diagnostic, Before, and After work, 43 real requests were made. Forty-two requests retained usage records; the known peak-price upper bound is about `$0.0237`. Even allowing the first unrecorded response to consume its full configured output allowance, the conservative total remains below `$0.026`.

## Remote Regression Evidence

[GitHub Actions Run 33375239707](https://github.com/Isoldelu/software-engineering-agent/actions/runs/33375239707) passed all three jobs on commit `3f83bdf`: `test-and-evaluate`, `docker-build`, and `postgres-integration`. The test job includes 160 tests, static checks, type checks, and the offline evaluation smoke. The workflow has no Provider credential and does not call `evaluation/real_provider_eval.py`, so this regression run incurred zero Provider calls. Real A/B reports are committed only after secret-shape scans and contain aggregate usage and redacted metadata, not credentials or raw model responses.

## Why Exact Deterministic Parity Is Secondary

Exact sequence equality is useful for drift visibility but is not a reliable Tool Accuracy label. For example, the deterministic Router selected only dependency analysis for a component-ownership-plus-dependency query, while DeepSeek correctly selected `component_mapping` and `dependency_analysis`. The final benchmark therefore uses human-labeled required Tool coverage as the primary routing metric and retains exact parity as a secondary comparison.

## Reproduction

```powershell
$env:DEEPSEEK_API_KEY="<local-secret>"
$env:SOFTWARE_AGENT_ENABLE_ONLINE_LLM="true"
$env:SOFTWARE_AGENT_LLM_PROVIDER="deepseek"
python -B evaluation/real_provider_eval.py --confirm-paid-calls --max-calls 20
```

Official references:

- [DeepSeek first API call](https://api-docs.deepseek.com/)
- [DeepSeek Chat Completions and JSON Output](https://api-docs.deepseek.com/api/create-chat-completion/)
- [DeepSeek models and pricing](https://api-docs.deepseek.com/quick_start/pricing/)

## Honest Boundaries

- Twenty labeled cases do not establish broad model quality or production SLA.
- This experiment evaluates JSON planning, not native multi-turn Tool Calls.
- No model training, fine-tuning, online learning, or autonomous source modification was performed.
- The deterministic Planner remains the zero-cost default and safety fallback.
