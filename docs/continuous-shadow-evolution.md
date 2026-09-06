# Trace-driven Continuous Shadow Evolution

## Purpose

Step 38 turns the existing one-shot offline evolution experiment into a resumable, bounded Trace
consumer. It detects observable quality drift and automatically evaluates safe configuration
candidates, while preserving the human approval and release boundary.

This is continuous **Shadow optimization**, not autonomous online learning. The service never edits
source code, changes evaluation data, approves a candidate, or activates a Policy.

## Architecture

```text
Trace Repository + Trace-linked Feedback
                 |
                 v
        Bounded batch + cursor
                 |
                 v
     Deterministic quality scoring
                 |
                 v
        Healthy reference profile
                 |
                 v
        Multi-signal drift check
                 |
          drift only
                 v
  Actionable failure clustering (support >= 2)
                 |
                 v
      Configuration candidate
                 |
                 v
  Shadow + frozen regression evaluation
                 |
                 v
           pending_review
                 |
          human decision only
                 v
    reviewed Policy bridge / rollout
```

## Quality Signals

`TraceQualityScorer` uses only observable Trace and Feedback fields. It does not store chain of
thought or ask an LLM to judge another LLM.

| Signal | Score impact | Candidate actionable |
|---|---:|---|
| execution failed | -0.55 | No, without a deterministic remedy |
| partial success | -0.25 | No |
| successful answer without Evidence | -0.30 | No |
| Verifier failed | -0.40 | No |
| duplicate Tool/input call | -0.20 | No |
| negative user feedback | -0.50 | Only for one explicit wrong-tool/expected-tool pair |

A score below `0.75` is low quality. Low quality and actionable are deliberately separate: the
system may observe a failure without inventing a configuration change.

## Drift And Baseline

The first batch initializes a reference profile only when mean quality is at least `0.90`, the
low-quality rate is at most `0.10`, and the failure rate is at most `0.05`. An unhealthy first
window raises `absolute_quality_threshold_breached` and cannot become the reference. Later batches
compare:

- mean quality score;
- low-quality rate;
- execution-failure rate;
- Tool-distribution total variation;
- P95 latency with an absolute noise floor.

The last healthy profile remains the baseline when drift is detected, so a degraded batch cannot
normalize itself into the reference. Candidate generation requires both detected drift and at least
two matching actionable traces.

## Persistence And Concurrency

The existing generic control-plane storage is reused for:

- `continuous_evolution_state`: cursor, processed count, and healthy baseline;
- `continuous_evolution_cycle`: immutable cycle summaries and Gate results;
- `continuous_trace_assessment`: per-Trace quality observations.

SQLite and PostgreSQL use the same repository contract. A database lease serializes each scan, and
the cursor advances only after assessments, cycle evidence, and candidate results are retained.
The cursor/reference state is protected from time-based retention; assessments retain 30 days and
cycle summaries retain 90 days by default.

## Safety Contract

- Batch size is bounded to `1..1000`.
- Each Trace is consumed once according to a persistent cursor.
- Only explicit negative `wrong_tool` feedback with one `expected_tool` can generate a candidate.
- Candidate types remain configuration-only and use the existing allowlist validator.
- Shadow evaluation replays linked failures and the 193-case frozen Agent set.
- Passing candidates stop at `pending_review` and `active=false`.
- Provider calls are not required; the deterministic local Agent is used for replay.

## API And Commands

```text
POST /evolution/continuous/scan
GET  /evolution/continuous/state
GET  /evaluation/evolution-continuous
```

Run the compact demo:

```bash
python -B examples/continuous_evolution_demo.py
```

Run the evidence-producing evaluation:

```bash
python -B evaluation/continuous_evolution_eval.py
```

## Verified Local Experiment

Two deterministic five-Trace windows were executed:

```text
healthy window:       5 traces, 0 low quality, reference initialized
degraded window:      5 traces, 3 low quality and actionable
drift signals:        quality score, low-quality rate, Tool distribution
candidate:            1 Router Rule, pending_review, inactive
linked fixes:         3/3
frozen regressions:   0
follow-up empty scan: idle, cursor unchanged
paid Provider calls:  0
```

The machine-readable result is retained in
[`evaluation/continuous_evolution_report.json`](../evaluation/continuous_evolution_report.json).

## Honest Boundary

Step 38 provides resumable Trace-driven scans, not an always-on scheduler or proof from production
traffic. It does not train model parameters, perform RL, self-edit Python, lower release Gates, or
approve its own candidate. A future scheduler may invoke the scan periodically, but human review
must remain between Shadow evaluation and Policy rollout.

## Interview Wording

> I extended the one-shot offline evolution experiment into a resumable Trace-driven Shadow loop.
> A bounded consumer scores observable execution quality, compares each batch with the last healthy
> profile, and only converts explicit repeated wrong-tool feedback into configuration candidates.
> In a two-window experiment it detected three quality-drift signals, fixed 3/3 linked routing cases,
> introduced zero frozen-set regressions, and stopped the candidate at pending review. It is controlled
> continuous optimization, not model training or autonomous deployment.
