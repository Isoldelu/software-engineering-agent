# Step 21: Multi-turn Context And Enhanced Trace

## Purpose

Step 21 adds bounded task context and replayable execution traces. It does not store hidden chain-of-thought. The stored data is limited to user inputs, resolved task entities, plans, Tool status/latency, Evidence IDs, verification output, and the final answer.

## Multi-turn Flow

```text
query + optional session_id
-> load AgentContext
-> resolve package/release/component references
-> Router / Planner / Tools / Verifier
-> update task-only context
-> record trace-v1
-> return session_id + trace_id
```

Example:

```text
query openssl package info
它的依赖是什么       -> openssl 它的依赖是什么
再比较版本           -> openssl 再比较版本
```

Explicit entities override inherited entities. Sessions never read entities from another session.

## AgentContext Schema

```text
session_id
turn_count
packages (maximum 8)
release
component
last_intent
last_tool
last_trace_id
recent_turns (bounded)
created_at / updated_at
```

`SessionRepository` is thread-safe and uses LRU-style bounded in-memory storage. Defaults are 100 sessions and 20 recent turn summaries per session. `DELETE /sessions/{session_id}` removes the context immediately.

## Trace Schema

Every call produces `trace-v1` with:

```text
trace_id / session_id / parent_trace_id
created_at / policy_version
input.original_query / resolved_query / inherited_entities
plan.intent / tool / arguments / steps / planner_source
steps[].tool / input / status / latency_ms / evidence_ids / error
output.answer / execution_status / citations / verification
metrics.total_latency_ms / tool_call_count / trace_complete
privacy.stores_internal_thought = false
```

The old `trajectory` remains for V1 compatibility. New audit, replay, and future Feedback logic should use `trace`.

## Replay

```text
GET  /traces/{trace_id}
GET  /traces/{trace_id}/replay-input
POST /traces/{trace_id}/replay
```

Replay reconstructs the exact resolved input and executes it in a new isolated session. The replay response includes `replay_of` and `replay_input`; it does not mutate the original session.

## Persistence And Privacy

- Traces are always available in bounded process memory.
- When `persist_trajectory=true`, `trace-v1` is also appended to `data/traces.jsonl` and the compatible trajectory record is appended to `data/trajectories.jsonl`.
- Session deletion does not delete historical audit traces.
- The JSONL files require an external retention/deletion policy in a production deployment.
- Context is not used for credentials, personal information, arbitrary conversation summaries, or internal Thought.

## Evaluation

Run:

```bash
python -B evaluation/eval_runner.py --suite context
```

The current set contains 8 conversations, 18 turns, 10 inheritance checks, and 5 cross-session isolation probes.

| Metric | Result | Threshold |
|---|---:|---:|
| Multi-turn entity consistency | 100% | >= 95% |
| Cross-session leaks | 0 | 0 |
| Trace completeness | 100% | 100% |
| Replay input reconstruction | 100% | 100% |

These results cover the simulated package/release/component domain and deterministic local workflow.
