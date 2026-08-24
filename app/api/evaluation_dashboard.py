"""Evaluation dashboard page for interview demos."""

EVALUATION_DASHBOARD_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Software-Agent Evaluation Dashboard</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1f2937;
      --muted: #667085;
      --line: #d7dce3;
      --accent: #1463ff;
      --ok: #0f8a4b;
      --code: #0f172a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      padding: 24px 32px 16px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 {
      margin: 0 0 6px;
      font-size: 24px;
      letter-spacing: 0;
    }
    .subtitle {
      color: var(--muted);
      font-size: 14px;
    }
    main {
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px;
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .metric, section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 8px;
    }
    .metric strong {
      font-size: 22px;
    }
    h2 {
      margin: 0 0 14px;
      font-size: 16px;
      letter-spacing: 0;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      text-align: left;
      border-bottom: 1px solid var(--line);
      padding: 10px 8px;
      vertical-align: top;
    }
    th {
      color: var(--muted);
      font-weight: 700;
    }
    .pass {
      color: var(--ok);
      font-weight: 700;
    }
    .fail {
      color: #b42318;
      font-weight: 700;
    }
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
      gap: 18px;
    }
    pre {
      margin: 0;
      background: var(--code);
      color: #e5e7eb;
      border-radius: 6px;
      padding: 14px;
      overflow: auto;
      max-height: 460px;
      font-size: 12px;
      line-height: 1.5;
    }
    button {
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: white;
      padding: 10px 14px;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
    }
    @media (max-width: 860px) {
      main { padding: 16px; }
      .summary, .layout { grid-template-columns: 1fr; }
      header { padding: 20px 18px 14px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Evaluation Dashboard</h1>
    <div class="subtitle">Benchmark, bad-case loop, and robustness metrics for the AI Software Engineering Agent.</div>
  </header>
  <main>
    <div class="summary">
      <div class="metric"><span>Total Suites</span><strong id="suiteCount">-</strong></div>
      <div class="metric"><span>Total Cases</span><strong id="totalCases">-</strong></div>
      <div class="metric"><span>Bad Cases</span><strong id="badCases">-</strong></div>
      <div class="metric"><span>All Passed</span><strong id="allPassed">-</strong></div>
    </div>
    <div class="layout">
      <section>
        <h2>Suite Metrics</h2>
        <table>
          <thead>
            <tr>
              <th>Suite</th>
              <th>Cases</th>
              <th>Routing</th>
              <th>Success</th>
              <th>Grounding</th>
              <th>Answer</th>
              <th>Avg Calls</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody id="suiteRows"></tbody>
        </table>
      </section>
      <section>
        <h2>Interview Highlights</h2>
        <div id="highlights"></div>
        <button id="reload">Reload Evaluation</button>
      </section>
    </div>
    <section style="margin-top: 18px;">
      <h2>Benchmark Experiment</h2>
      <table>
        <thead>
          <tr>
            <th>Method</th>
            <th>Task Success</th>
            <th>Answer Accuracy</th>
            <th>Tool Accuracy</th>
            <th>Avg Calls</th>
          </tr>
        </thead>
        <tbody id="methodRows"></tbody>
      </table>
    </section>
    <section style="margin-top: 18px;">
      <h2>Optimization</h2>
      <pre id="optimization">{}</pre>
    </section>
    <section style="margin-top: 18px;">
      <h2>Hybrid RAG Ablation</h2>
      <table>
        <thead>
          <tr><th>Mode</th><th>Recall@3</th><th>Recall@5</th><th>MRR</th><th>No Answer</th><th>Citation</th></tr>
        </thead>
        <tbody id="ragRows"></tbody>
      </table>
    </section>
    <section style="margin-top: 18px;">
      <h2>Context And Trace</h2>
      <table>
        <thead><tr><th>Entity Consistency</th><th>Session Leaks</th><th>Trace Complete</th><th>Replay Input</th><th>Status</th></tr></thead>
        <tbody id="contextRows"></tbody>
      </table>
    </section>
    <section style="margin-top: 18px;">
      <h2>Controlled Feedback Loop</h2>
      <table>
        <thead><tr><th>Feedback</th><th>Baseline</th><th>Candidate</th><th>Fixed</th><th>Regressions</th><th>Latency</th><th>Status</th></tr></thead>
        <tbody id="feedbackRows"></tbody>
      </table>
    </section>
    <section style="margin-top: 18px;">
      <h2>Policy Rollout And Rollback</h2>
      <table>
        <thead><tr><th>Target</th><th>Observed</th><th>Control Tool</th><th>Rollout Tool</th><th>Rollback</th><th>Source Unchanged</th><th>Status</th></tr></thead>
        <tbody id="policyRows"></tbody>
      </table>
    </section>
    <section style="margin-top: 18px;">
      <h2>Provider Dual Mode</h2>
      <table>
        <thead><tr><th>Cases</th><th>Plan Parity</th><th>Mock Online Calls</th><th>Fallback Modes</th><th>Paid Calls</th><th>Status</th></tr></thead>
        <tbody id="providerRows"></tbody>
      </table>
    </section>
    <section style="margin-top: 18px;">
      <h2>Raw Summary</h2>
      <pre id="raw">{}</pre>
    </section>
  </main>
  <script>
    const pct = (value) => `${(value * 100).toFixed(1)}%`;
    const num = (value) => Number(value).toFixed(2);

    async function loadSummary() {
      const [summaryResponse, ragResponse, contextResponse, feedbackResponse, policyResponse, providerResponse] = await Promise.all([
        fetch("/evaluation/summary"),
        fetch("/evaluation/rag"),
        fetch("/evaluation/context"),
        fetch("/evaluation/feedback"),
        fetch("/evaluation/policy"),
        fetch("/evaluation/provider")
      ]);
      const data = await summaryResponse.json();
      const rag = await ragResponse.json();
      const context = await contextResponse.json();
      const feedback = await feedbackResponse.json();
      const policy = await policyResponse.json();
      const provider = await providerResponse.json();
      document.getElementById("suiteCount").textContent = data.summary.suite_count;
      document.getElementById("totalCases").textContent = data.summary.total_cases;
      document.getElementById("badCases").textContent = data.summary.total_bad_cases;
      document.getElementById("allPassed").textContent = data.summary.all_suites_passed ? "true" : "false";

      document.getElementById("suiteRows").innerHTML = data.suites.map((suite) => `
        <tr>
          <td>${suite.benchmark}</td>
          <td>${suite.total}</td>
          <td>${pct(suite.tool_routing_accuracy)}</td>
          <td>${pct(suite.task_success_rate)}</td>
          <td>${pct(suite.answer_grounding_accuracy)}</td>
          <td>${pct(suite.answer_accuracy)}</td>
          <td>${num(suite.average_tool_calls)}</td>
          <td class="${suite.passed ? "pass" : "fail"}">${suite.passed ? "pass" : "review"}</td>
        </tr>
      `).join("");

      document.getElementById("highlights").innerHTML = data.interview_highlights
        .map((item) => `<p>${item}</p>`)
        .join("");
      document.getElementById("methodRows").innerHTML = data.experiment.methods.map((method) => `
        <tr>
          <td>${method.method}</td>
          <td>${pct(method.task_success_rate)}</td>
          <td>${pct(method.answer_accuracy)}</td>
          <td>${method.tool_accuracy === null ? "N/A" : pct(method.tool_accuracy)}</td>
          <td>${num(method.average_tool_calls)}</td>
        </tr>
      `).join("");
      document.getElementById("optimization").textContent = JSON.stringify(data.experiment.optimization, null, 2);
      document.getElementById("ragRows").innerHTML = Object.values(rag.modes).map((mode) => `
        <tr>
          <td>${mode.mode}</td><td>${pct(mode.recall_at_3)}</td><td>${pct(mode.recall_at_5)}</td>
          <td>${pct(mode.mrr)}</td><td>${pct(mode.no_answer_accuracy)}</td><td>${pct(mode.citation_correctness)}</td>
        </tr>
      `).join("");
      document.getElementById("contextRows").innerHTML = `
        <tr>
          <td>${pct(context.entity_consistency)}</td>
          <td>${context.cross_session_leak_count}</td>
          <td>${pct(context.trace_completeness)}</td>
          <td>${pct(context.replay_input_reconstruction)}</td>
          <td class="${context.passed ? "pass" : "fail"}">${context.passed ? "pass" : "review"}</td>
        </tr>`;
      document.getElementById("feedbackRows").innerHTML = `
        <tr>
          <td>${feedback.feedback_count}</td>
          <td>${pct(feedback.baseline_score)}</td>
          <td>${pct(feedback.candidate_score)}</td>
          <td>${feedback.fixed_bad_case_count}</td>
          <td>${feedback.regressed_case_count} / ${feedback.regression_case_count}</td>
          <td>${pct(feedback.added_latency_ratio)}</td>
          <td class="${feedback.passed ? "pass" : "fail"}">${feedback.candidate_status} / ${feedback.candidate_active ? "active" : "inactive"}</td>
        </tr>`;
      document.getElementById("policyRows").innerHTML = `
        <tr>
          <td>${pct(policy.rollout_percentage / 100)}</td>
          <td>${pct(policy.observed_rollout_rate)}</td>
          <td>${policy.control.selected_tool}</td>
          <td>${policy.rollout.selected_tool}</td>
          <td>${policy.rollback_event?.action || "none"}</td>
          <td>${policy.source_hash_before === policy.source_hash_after ? "true" : "false"}</td>
          <td class="${policy.passed ? "pass" : "fail"}">${policy.passed ? "pass" : "review"}</td>
        </tr>`;
      document.getElementById("providerRows").innerHTML = `
        <tr>
          <td>${provider.case_count}</td>
          <td>${pct(provider.offline_online_plan_parity)}</td>
          <td>${provider.online_mock_calls}</td>
          <td>${Object.keys(provider.fallback_cases).length}</td>
          <td>${provider.paid_api_calls}</td>
          <td class="${provider.passed ? "pass" : "fail"}">${provider.passed ? "pass" : "review"}</td>
        </tr>`;
      document.getElementById("raw").textContent = JSON.stringify(data, null, 2);
    }

    document.getElementById("reload").addEventListener("click", loadSummary);
    loadSummary();
  </script>
</body>
</html>
"""
