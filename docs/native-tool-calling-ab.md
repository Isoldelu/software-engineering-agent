# DeepSeek Native Tool Calling A/B

## Purpose

Step 36 compares three execution paths on the same ten simulated AI4SE queries:

1. deterministic Planner and local Tools;
2. DeepSeek JSON Planner followed by the existing local Workflow;
3. DeepSeek native Tool Calling with a bounded model/tool loop.

The comparison measures Tool-call validity, Required Tool coverage, task success, average Provider
rounds, average Tool calls, P50/P95 Provider latency, token usage, fallback, and conservative cost.

## Why Native Tool Calling Is Different

The JSON Planner returns one complete plan before execution. Native Tool Calling instead receives
function schemas, emits one or more function calls, observes local Tool results, and may continue in
a later Provider round. This lets the model adapt after a release lookup, but it also introduces new
failure modes: malformed arguments, unknown Tools, repeated calls, excessive rounds, and higher
context cost.

## Controlled Architecture

```text
User Query
-> DeepSeek native tools request (first round requires at least one Tool)
-> local Tool allowlist and exact argument validation
-> deterministic Tool execution over simulated data
-> compact Tool observation returned to DeepSeek
-> final grounded answer or another bounded Tool round
```

Controls:

- online mode is opt-in and requires `DEEPSEEK_API_KEY` in the current process;
- maximum 10 benchmark cases, 3 Native rounds per case, and 40 projected Provider requests;
- maximum 8 attempted Tool calls per case;
- unknown Tools, invalid JSON, extra arguments, empty queries, and oversized queries are blocked;
- exact duplicate Tool/query pairs are blocked locally;
- an all-`not_found` Tool round forces the next Provider turn to answer without more Tools;
- Tool observations remain authoritative and model output never bypasses local validation;
- reports exclude credentials, raw message history, raw model answers, and Tool evidence payloads;
- CI and the default evaluation suite never execute this paid runner.

## Secure Key Rotation And Run

Revoke the previously shared Key in the official DeepSeek Platform and create a replacement. Do not
paste the replacement into chat, source files, `.env`, PowerShell history, or GitHub Secrets for this
local experiment.

Run the helper from a local PowerShell terminal. It uses hidden input, places the Key only in the
child process environment, clears the environment variable in `finally`, and writes a sanitized
report:

```powershell
./examples/run_step36.ps1 -PythonCommand "python" -SdkPath "<temporary-sdk-directory>" -MaxCases 10
```

When Python is not on `PATH`, pass its absolute executable path with `-PythonCommand`.

## Real Before/After Results

The same ten simulated queries were evaluated before and after the convergence changes. The model,
non-thinking mode, local Tools, labels, round limit, and conservative peak-price calculation stayed
the same.

| Native metric | Before | After | Change |
|---|---:|---:|---:|
| Tool-call validity | 100% | 100% | unchanged |
| Required Tool accuracy | 100% | 100% | unchanged |
| Run validity | 90% | 100% | +10 pp |
| Task success | 90% | 100% | +10 pp |
| Average Provider rounds | 2.4 | 2.3 | -4.17% |
| Average Tool calls | 2.4 | 1.7 | -29.17% |
| P50 Provider latency | 2704 ms | 2570 ms | -4.97% |
| P95 Provider latency | 5940 ms | 4074 ms | -31.41% |
| Total tokens | 31,393 | 27,900 | -11.13% |
| Peak-price cost upper bound | $0.016078 | $0.013977 | -13.07% |

The optimized three-way run produced these method-level results:

| Method | Required Tool accuracy | Task success | Avg Tool calls | P95 | Cost upper bound |
|---|---:|---:|---:|---:|---:|
| Deterministic Planner | 90% | 90% | 1.9 | 33 ms | $0 |
| JSON Planner | 100% | 100% | 1.7 | 6155 ms | $0.005775 |
| Native Tool Calling | 100% | 100% | 1.7 | 4074 ms | $0.013977 |

The version-comparison Bad Case fell from four Tools and 6,683 tokens to one `version_compare`
call and 2,121 tokens. The missing `1215` release fell from five calls ending in
`max_rounds_exceeded` to one `package_search` observation followed by a grounded `not_found`
answer.

Artifacts:

- [`native_tool_calling_report_before.json`](../evaluation/native_tool_calling_report_before.json)
- [`native_tool_calling_report_after.json`](../evaluation/native_tool_calling_report_after.json)
- [`native_tool_calling_report_environment_failure.json`](../evaluation/native_tool_calling_report_environment_failure.json)

The environment-failure report records a zero-token SDK import failure that was caught before a
valid experiment. The runner now preflights `from openai import OpenAI` before asking for a Key.
The final report passed every Gate and a generic credential-shape scan found no Key.

## Official References

- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)
- [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)
- [DeepSeek Models and Pricing](https://api-docs.deepseek.com/quick_start/pricing/)

## Honest Boundaries

- This is a ten-query simulated benchmark, not a production SLA or broad model evaluation.
- Task success is based on required local Tools and deterministic observation status; it is not a
  general semantic-answer benchmark.
- The model cannot execute shell commands, access arbitrary files, add Tools, change source, approve
  candidates, or publish policies.
- Step 36 evaluates inference-time Tool use, not training, fine-tuning, RL, or online self-learning.
- The two paid runs are subject to Provider variance; the measured deltas establish this controlled
  experiment, not a universal ranking of planning methods.
