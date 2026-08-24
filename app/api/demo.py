"""Browser demo page for the Agent API."""

DEMO_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI Software Engineering Agent Demo</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1f2937;
      --muted: #667085;
      --line: #d7dce3;
      --accent: #1463ff;
      --accent-dark: #0f4dc8;
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
      font-weight: 700;
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
      display: grid;
      grid-template-columns: minmax(280px, 380px) 1fr;
      gap: 20px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }
    h2 {
      margin: 0 0 14px;
      font-size: 16px;
      letter-spacing: 0;
    }
    label {
      display: block;
      margin: 12px 0 6px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
    }
    textarea, input, select {
      width: 100%;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      font: 14px Arial, Helvetica, sans-serif;
      color: var(--text);
    }
    textarea { min-height: 110px; resize: vertical; }
    button {
      width: 100%;
      margin-top: 14px;
      padding: 11px 14px;
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: white;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
    }
    button:hover { background: var(--accent-dark); }
    button:disabled { opacity: 0.65; cursor: default; }
    .examples {
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }
    .example {
      width: 100%;
      text-align: left;
      background: #eef3ff;
      color: #163b7a;
      font-weight: 600;
      margin: 0;
    }
    .secondary { background: #e5e7eb; color: #1f2937; }
    .secondary:hover { background: #d1d5db; }
    .feedback-status { margin-top: 10px; color: var(--muted); font-size: 13px; }
    .navlink {
      display: block;
      margin-top: 14px;
      padding: 11px 14px;
      border-radius: 6px;
      background: #f1f5f9;
      color: #1f2937;
      text-decoration: none;
      font-size: 14px;
      font-weight: 700;
      text-align: center;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 14px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      min-height: 72px;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 8px;
    }
    .metric strong {
      font-size: 18px;
      overflow-wrap: anywhere;
    }
    pre {
      margin: 0;
      background: var(--code);
      color: #e5e7eb;
      border-radius: 6px;
      padding: 14px;
      overflow: auto;
      max-height: 520px;
      font-size: 12px;
      line-height: 1.5;
    }
    .answer {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      margin-bottom: 14px;
      line-height: 1.55;
      background: #fbfcfe;
    }
    @media (max-width: 840px) {
      main { grid-template-columns: 1fr; padding: 16px; }
      .grid { grid-template-columns: 1fr; }
      header { padding: 20px 18px 14px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>AI Software Engineering Agent</h1>
    <div class="subtitle">Package analysis, dependency reasoning, RAG retrieval, and hybrid tool planning.</div>
  </header>
  <main>
    <section>
      <h2>Query</h2>
      <label for="session">Session</label>
      <input id="session" value="demo-session" />
      <button class="secondary" id="clearSession">Clear Session</button>
      <label for="query">User query</label>
      <textarea id="query">1214 release packages and their dependencies</textarea>
      <label for="providerMode">Planner provider</label>
      <select id="providerMode">
        <option value="offline">Offline deterministic</option>
        <option value="auto">Auto from environment</option>
        <option value="openai">OpenAI with safe fallback</option>
      </select>
      <button id="run">Run Agent</button>
      <label>Examples</label>
      <div class="examples">
        <button class="example" data-query="query openssl version">Package version lookup</button>
        <button class="example" data-query="which package owns libpcap.so">Component mapping</button>
        <button class="example" data-query="release note says what was added in 1214">RAG release note</button>
        <button class="example" data-query="1214 release packages and their dependencies">Hybrid planning</button>
        <button class="example" data-query="查一下 nginx 的版本变化和依赖">Robustness multi-intent</button>
        <button class="example" data-query="libpcap.so 是谁依赖引入的？">Reverse dependency</button>
        <button class="example" data-query="query openssl package info">Multi-turn 1: select openssl</button>
        <button class="example" data-query="它的依赖是什么">Multi-turn 2: dependency</button>
        <button class="example" data-query="再比较版本">Multi-turn 3: version</button>
      </div>
      <a class="navlink" href="/evaluation-dashboard">Open Evaluation Dashboard</a>
      <label for="expectedTool">Expected tool for feedback</label>
      <select id="expectedTool">
        <option value="dependency_analysis">Dependency Analysis</option>
        <option value="package_search">Package Search</option>
        <option value="version_compare">Version Compare</option>
        <option value="component_mapping">Component Mapping</option>
        <option value="rag_retrieval">RAG Retrieval</option>
      </select>
      <button class="secondary" id="reportWrongTool">Report Wrong Tool</button>
      <div class="feedback-status" id="feedbackStatus">Run a query before submitting feedback.</div>
    </section>
    <section>
      <h2>Result</h2>
      <div class="grid">
        <div class="metric"><span>Intent</span><strong id="intent">-</strong></div>
        <div class="metric"><span>Tool Calls</span><strong id="toolCalls">-</strong></div>
        <div class="metric"><span>Execution Status</span><strong id="success">-</strong></div>
        <div class="metric"><span>Citations</span><strong id="citations">-</strong></div>
        <div class="metric"><span>Policy</span><strong id="policy">-</strong></div>
        <div class="metric"><span>Provider</span><strong id="provider">-</strong></div>
      </div>
      <div class="answer" id="answer">Run a query to inspect the Agent answer.</div>
      <h2>Plan And Trajectory</h2>
      <pre id="details">{}</pre>
    </section>
  </main>
  <script>
    const queryEl = document.getElementById("query");
    const sessionEl = document.getElementById("session");
    const runBtn = document.getElementById("run");
    const providerModeEl = document.getElementById("providerMode");
    const clearSessionBtn = document.getElementById("clearSession");
    const intentEl = document.getElementById("intent");
    const toolCallsEl = document.getElementById("toolCalls");
    const successEl = document.getElementById("success");
    const citationsEl = document.getElementById("citations");
    const policyEl = document.getElementById("policy");
    const providerEl = document.getElementById("provider");
    const answerEl = document.getElementById("answer");
    const detailsEl = document.getElementById("details");
    const expectedToolEl = document.getElementById("expectedTool");
    const reportWrongToolBtn = document.getElementById("reportWrongTool");
    const feedbackStatusEl = document.getElementById("feedbackStatus");
    let currentTraceId = null;

    document.querySelectorAll(".example").forEach((button) => {
      button.addEventListener("click", () => {
        queryEl.value = button.dataset.query;
      });
    });

    clearSessionBtn.addEventListener("click", async () => {
      await fetch(`/sessions/${encodeURIComponent(sessionEl.value)}`, { method: "DELETE" });
      answerEl.textContent = "Session context cleared.";
      detailsEl.textContent = "{}";
    });

    reportWrongToolBtn.addEventListener("click", async () => {
      if (!currentTraceId) {
        feedbackStatusEl.textContent = "Run a query before submitting feedback.";
        return;
      }
      const response = await fetch("/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trace_id: currentTraceId,
          rating: -1,
          issue_type: "wrong_tool",
          expected_tool: expectedToolEl.value,
          comment: "Submitted from the local Step 22 demo."
        })
      });
      const data = await response.json();
      feedbackStatusEl.textContent = response.ok
        ? `Feedback ${data.feedback_id} recorded for ${data.fingerprint}.`
        : (data.detail || "Feedback submission failed.");
    });

    runBtn.addEventListener("click", async () => {
      runBtn.disabled = true;
      answerEl.textContent = "Running Agent...";
      detailsEl.textContent = "{}";
      try {
        const response = await fetch("/agent/query-provider", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: queryEl.value,
            session_id: sessionEl.value || null,
            persist_trajectory: false,
            provider: providerModeEl.value,
            allow_fallback: true
          })
        });
        const data = await response.json();
        intentEl.textContent = data.intent || "-";
        toolCallsEl.textContent = String(data.tool_call_count ?? "-");
        successEl.textContent = data.execution_status || (data.success ? "success" : "failed");
        citationsEl.textContent = String(data.evidence_count ?? 0);
        policyEl.textContent = data.policy_version || "-";
        providerEl.textContent = data.provider?.effective_provider || "-";
        sessionEl.value = data.session_id || sessionEl.value;
        currentTraceId = data.trace_id || null;
        feedbackStatusEl.textContent = currentTraceId
          ? `Current trace: ${currentTraceId}`
          : "No replayable trace returned.";
        answerEl.textContent = data.answer || "";
        detailsEl.textContent = JSON.stringify({
          used_tools: data.used_tools,
          plan: data.plan,
          evidence: data.evidence,
          evidence_items: data.evidence_items,
          citations: data.citations,
          evidence_count: data.evidence_count,
          execution_status: data.execution_status,
          verification: data.verification,
          session_id: data.session_id,
          trace_id: data.trace_id,
          parent_trace_id: data.parent_trace_id,
          resolved_query: data.resolved_query,
          inherited_context: data.inherited_context,
          context: data.context,
          trace: data.trace,
          policy_version: data.policy_version,
          policy_assignment: data.policy_assignment,
          policy_monitor_event: data.policy_monitor_event,
          provider: data.provider,
          trajectory: data.trajectory
        }, null, 2);
      } catch (error) {
        answerEl.textContent = String(error);
      } finally {
        runBtn.disabled = false;
      }
    });
  </script>
</body>
</html>
"""
