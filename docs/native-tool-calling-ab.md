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

## Current Status

- Native Tool agent, hard limits, local validation, three-way evaluator, and secure runner: complete.
- Mock Provider contract and three-way comparison tests: complete.
- Local full regression: 165 tests passed.
- Real 10-case comparison: pending a rotated Key entered locally through the secure runner.

No real Step 36 metric should be claimed until `evaluation/native_tool_calling_report.json` exists,
passes all gates, and is scanned for credential-shaped values.

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
