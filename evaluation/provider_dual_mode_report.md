# Step 24 Provider Dual-mode Evaluation

## Design

Twelve representative package, dependency, version, component, RAG, and Hybrid queries were executed through both the deterministic Offline Provider and a scripted Mock Online Provider. The mock follows the same structured-output contract as the optional OpenAI adapter but makes no network call.

Three failures were injected: malformed JSON, unknown Tool, and timeout. A fourth check disabled fallback to verify fail-closed behavior.

## Results

| Metric | Result |
|---|---:|
| Evaluation cases | 12 |
| Offline/Mock-Online plan parity | 100% |
| Provider metadata recorded in Trace | 100% |
| Injected failure modes | 3 |
| Safe fallback rate | 100% |
| Fallback task success | 100% |
| Fail-closed when fallback disabled | Passed |
| Online calls per evaluated query | 1 |
| Paid API calls | 0 |

## Boundary

This result verifies provider integration, schema validation, fallback, attribution, and call bounding. It does not claim real-model quality because no paid external API was called. Real-provider quality and cost should be reported as a separate opt-in experiment after an API key and budget are explicitly provided.
