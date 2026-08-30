import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { Presentation, PresentationFile } from "@oai/artifact-tool";

const ROOT = process.env.PROJECT_ROOT
  ? path.resolve(process.env.PROJECT_ROOT)
  : path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const OUTPUT = path.resolve(
  process.argv[2] ?? path.join(ROOT, "docs", "Software-Agent-Interview-Deck.pptx"),
);

const W = 1280;
const H = 720;
const FONT = "Microsoft YaHei";
const MONO = "Consolas";
const C = {
  ink: "#17212B",
  muted: "#5F6B76",
  faint: "#E8ECEF",
  panel: "#F3F6F7",
  teal: "#0B7A75",
  tealLight: "#DCEFEB",
  blue: "#3973D4",
  blueLight: "#E7EFFB",
  amber: "#C88422",
  amberLight: "#F9EDD9",
  green: "#247A4A",
  red: "#B4473D",
  white: "#FFFFFF",
};

function addText(slide, text, position, options = {}) {
  const box = slide.shapes.add({
    geometry: "textbox",
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  box.text = text;
  box.text.style = {
    fontSize: options.fontSize ?? 22,
    typeface: options.typeface ?? FONT,
    color: options.color ?? C.ink,
    bold: options.bold ?? false,
    alignment: options.alignment ?? "left",
    verticalAlignment: options.verticalAlignment ?? "top",
    autoFit: options.autoFit ?? "shrinkText",
    wrap: options.wrap ?? "square",
    insets: options.insets ?? { top: 0, right: 0, bottom: 0, left: 0 },
  };
  return box;
}

function addRect(slide, position, fill, options = {}) {
  return slide.shapes.add({
    geometry: options.geometry ?? "rect",
    position,
    fill,
    line: options.line ?? { style: "solid", fill: fill, width: 0 },
    ...(options.borderRadius ? { borderRadius: options.borderRadius } : {}),
  });
}

function addRule(slide, left, top, width, color = C.faint, height = 2) {
  return addRect(slide, { left, top, width, height }, color);
}

function addSlideNumber(slide, value) {
  addText(slide, String(value).padStart(2, "0"), { left: 1185, top: 666, width: 52, height: 20 }, {
    fontSize: 14,
    color: C.muted,
    alignment: "right",
  });
}

function addHeader(slide, title, number) {
  addText(slide, title, { left: 56, top: 38, width: 1120, height: 54 }, {
    fontSize: 42,
    bold: true,
  });
  addRule(slide, 56, 106, 1168, C.faint, 2);
  addSlideNumber(slide, number);
}

function setNotes(slide, talkTrack, sources) {
  slide.speakerNotes.textFrame.setText(
    `${talkTrack}\n\n[Sources]\n${sources.map((source) => `- ${source}`).join("\n")}`,
  );
  slide.speakerNotes.setVisible(true);
}

async function imageBytes(relativePath) {
  const bytes = await fs.readFile(path.join(ROOT, relativePath));
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

function buildCover(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addRect(slide, { left: 0, top: 0, width: 16, height: H }, C.teal);
  addText(slide, "AI4SE · INTERVIEW DECK", { left: 64, top: 58, width: 470, height: 28 }, {
    fontSize: 17,
    bold: true,
    color: C.teal,
  });
  addText(slide, "Software\nEngineering Agent", { left: 64, top: 150, width: 790, height: 210 }, {
    fontSize: 70,
    bold: true,
    autoFit: "none",
  });
  addText(
    slide,
    "面向软件研发场景的多工具检索、分析与受控优化系统",
    { left: 68, top: 392, width: 800, height: 50 },
    { fontSize: 26, color: C.muted },
  );

  addRect(slide, { left: 902, top: 72, width: 322, height: 506 }, C.ink);
  addText(slide, "Agent", { left: 938, top: 118, width: 248, height: 55 }, {
    fontSize: 46,
    bold: true,
    color: C.white,
  });
  addText(slide, "Tools\nEvidence\nVerifier\nTrace\nEvaluation", { left: 940, top: 212, width: 240, height: 270 }, {
    fontSize: 31,
    color: "#B9DCD8",
    autoFit: "none",
  });
  addRule(slide, 64, 520, 770, C.faint, 2);
  addText(slide, "138", { left: 68, top: 548, width: 116, height: 52 }, { fontSize: 40, bold: true, color: C.teal });
  addText(slide, "tests", { left: 68, top: 604, width: 116, height: 26 }, { fontSize: 17, color: C.muted });
  addText(slide, "193", { left: 286, top: 548, width: 116, height: 52 }, { fontSize: 40, bold: true, color: C.blue });
  addText(slide, "frozen cases", { left: 286, top: 604, width: 150, height: 26 }, { fontSize: 17, color: C.muted });
  addText(slide, "0", { left: 522, top: 548, width: 116, height: 52 }, { fontSize: 40, bold: true, color: C.amber });
  addText(slide, "paid API calls", { left: 522, top: 604, width: 180, height: 26 }, { fontSize: 17, color: C.muted });
  addText(slide, "公开模拟数据 · 个人方法论复现", { left: 64, top: 671, width: 600, height: 20 }, {
    fontSize: 15,
    color: C.muted,
  });
  addSlideNumber(slide, 1);
  setNotes(
    slide,
    "这不是华为内部系统的复刻，而是我基于公开风格模拟数据完成的个人方法论复现。项目目标是验证多工具 Agent 在软件资产查询、依赖分析、版本比较和研发文档检索中的完整闭环。",
    [
      "Local README: README.md",
      "Local compliance audit: docs/public-release-audit.md",
      "Current CI evidence: https://github.com/Isoldelu/software-engineering-agent/actions/runs/33314875879",
    ],
  );
}

function buildArchitecture(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addHeader(slide, "它不是普通 RAG，而是一条可验证的 Agent 执行链", 2);

  const nodes = [
    ["Query + Context", "多轮实体解析", C.panel],
    ["Planner + Router", "单工具 / Hybrid", C.tealLight],
    ["Tool Execution", "5 个领域工具", C.blueLight],
    ["Evidence + Verifier", "引用与部分成功", C.amberLight],
    ["Answer + Trace", "可回放执行轨迹", C.panel],
  ];
  const lefts = [56, 294, 532, 770, 1008];

  for (let i = 0; i < 4; i += 1) {
    addText(slide, "→", { left: lefts[i] + 196, top: 205, width: 38, height: 44 }, {
      fontSize: 33,
      bold: true,
      color: C.teal,
      alignment: "center",
      verticalAlignment: "middle",
    });
  }
  nodes.forEach(([title, detail, fill], index) => {
    addRect(slide, { left: lefts[index], top: 166, width: 198, height: 128 }, fill, {
      line: { style: "solid", fill: index === 1 ? C.teal : C.faint, width: index === 1 ? 2 : 1 },
    });
    addText(slide, title, { left: lefts[index] + 16, top: 188, width: 166, height: 38 }, {
      fontSize: 22,
      bold: true,
      alignment: "center",
    });
    addText(slide, detail, { left: lefts[index] + 14, top: 244, width: 170, height: 28 }, {
      fontSize: 16,
      color: C.muted,
      alignment: "center",
    });
  });

  addText(slide, "知识与工具层", { left: 56, top: 350, width: 180, height: 34 }, {
    fontSize: 25,
    bold: true,
  });
  addRule(slide, 238, 368, 986, C.faint, 2);

  const sources = [
    ["Structured Assets", "Package · Dependency\nVersion · Component", C.teal],
    ["Hybrid RAG", "Legacy + BM25 + RRF\nReranker + No-answer", C.blue],
    ["Control Plane", "Policy · Feedback · Audit\nPostgreSQL · Metrics", C.amber],
  ];
  const sourceLefts = [56, 438, 820];
  sources.forEach(([title, detail, accent], index) => {
    addRule(slide, sourceLefts[index], 424, 332, accent, 6);
    addText(slide, title, { left: sourceLefts[index], top: 452, width: 330, height: 36 }, {
      fontSize: 27,
      bold: true,
    });
    addText(slide, detail, { left: sourceLefts[index], top: 504, width: 330, height: 76 }, {
      fontSize: 20,
      color: C.muted,
      autoFit: "none",
    });
  });
  addText(
    slide,
    "Trace → Evaluation → Bad-case Mining → Shadow Candidate → Human Review → Rollout / Rollback",
    { left: 56, top: 620, width: 1130, height: 34 },
    { fontSize: 20, bold: true, color: C.teal, alignment: "center" },
  );
  setNotes(
    slide,
    "核心区别是先规划、再调用工具、再收集 Evidence，最后由确定性 Verifier 判断是否满足任务。Trace 同时进入评测和受控优化环路，候选策略只能经过 Shadow、全量回归和人工审核后发布，并支持灰度与回滚。",
    [
      "Local architecture: docs/architecture-v2.md",
      "Evidence and citation contract: docs/evidence-citation.md",
      "Controlled evolution: docs/offline-controlled-evolution.md",
      "Policy rollout: docs/policy-rollout.md",
    ],
  );
}

async function buildQueryEvidence(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addHeader(slide, "一个复合问题触发 3 个工具，并返回可追溯事实", 3);
  addText(slide, "“查一下 nginx 的版本变化和依赖”", { left: 56, top: 124, width: 780, height: 42 }, {
    fontSize: 28,
    bold: true,
    color: C.teal,
  });
  addRect(slide, { left: 56, top: 178, width: 760, height: 470 }, C.panel, {
    line: { style: "solid", fill: C.faint, width: 1 },
  });
  slide.images.add({
    blob: await imageBytes("docs/assets/agent-demo.png"),
    contentType: "image/png",
    alt: "Software Agent demo showing a compound nginx query, three selected tools, evidence, citations, verifier, and trace summary",
    fit: "contain",
    position: { left: 64, top: 186, width: 744, height: 454 },
  });

  addText(slide, "PLAN", { left: 858, top: 180, width: 150, height: 24 }, { fontSize: 16, bold: true, color: C.muted });
  addText(slide, "Package Search\nDependency Analysis\nVersion Compare", { left: 858, top: 218, width: 330, height: 120 }, {
    fontSize: 25,
    bold: true,
    autoFit: "none",
  });
  addRule(slide, 858, 362, 330, C.faint, 2);
  addText(slide, "3", { left: 858, top: 392, width: 70, height: 50 }, { fontSize: 42, bold: true, color: C.teal });
  addText(slide, "Evidence", { left: 928, top: 408, width: 120, height: 28 }, { fontSize: 18, color: C.muted });
  addText(slide, "3", { left: 858, top: 466, width: 70, height: 50 }, { fontSize: 42, bold: true, color: C.blue });
  addText(slide, "Citations", { left: 928, top: 482, width: 120, height: 28 }, { fontSize: 18, color: C.muted });
  addText(slide, "PASS", { left: 858, top: 540, width: 122, height: 44 }, { fontSize: 35, bold: true, color: C.green });
  addText(slide, "Verifier + Trace", { left: 858, top: 590, width: 220, height: 28 }, { fontSize: 18, color: C.muted });
  setNotes(
    slide,
    "现场只演示一个复合 Query。Planner 没有靠单个关键词直接结束，而是组合 Package、Dependency、Version 三个工具。每个工具输出都被标准化成 Evidence 和 Citation，Verifier 通过，Trace 完整可回放。",
    [
      "Local browser screenshot: docs/assets/agent-demo.png",
      "Executable demo: examples/interview_demo.py",
      "Demo runbook: docs/demo-runbook.md",
    ],
  );
}

async function buildEvaluation(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addHeader(slide, "评测让优化可量化，也暴露了离线结果的边界", 4);

  addText(slide, "22.94%", { left: 56, top: 146, width: 180, height: 54 }, { fontSize: 42, bold: true, color: C.red });
  addText(slide, "DirectLLMProxy", { left: 56, top: 207, width: 190, height: 28 }, { fontSize: 17, color: C.muted });
  addText(slide, "57.06%", { left: 300, top: 146, width: 180, height: 54 }, { fontSize: 42, bold: true, color: C.blue });
  addText(slide, "RAGOnlyProxy", { left: 300, top: 207, width: 190, height: 28 }, { fontSize: 17, color: C.muted });
  addText(slide, "100%", { left: 544, top: 146, width: 180, height: 54 }, { fontSize: 42, bold: true, color: C.green });
  addText(slide, "Agent", { left: 544, top: 207, width: 190, height: 28 }, { fontSize: 17, color: C.muted });

  addRect(slide, { left: 56, top: 272, width: 705, height: 370 }, C.panel, {
    line: { style: "solid", fill: C.faint, width: 1 },
  });
  slide.images.add({
    blob: await imageBytes("docs/assets/evaluation-dashboard.png"),
    contentType: "image/png",
    alt: "Evaluation dashboard showing 193 frozen cases, no bad cases, offline baseline comparison, and optimization results",
    fit: "contain",
    position: { left: 64, top: 280, width: 689, height: 354 },
  });

  addText(slide, "Router 优化", { left: 816, top: 150, width: 300, height: 36 }, { fontSize: 26, bold: true });
  addText(slide, "61.76%  →  100%", { left: 816, top: 200, width: 360, height: 48 }, {
    fontSize: 34,
    bold: true,
    color: C.teal,
  });
  addText(slide, "alias mapping\ntool description\nhybrid planner\nbad-case regression", { left: 816, top: 286, width: 340, height: 150 }, {
    fontSize: 23,
    color: C.ink,
    autoFit: "none",
  });
  addRule(slide, 816, 466, 360, C.faint, 2);
  addText(slide, "193 / 193", { left: 816, top: 496, width: 220, height: 48 }, { fontSize: 38, bold: true, color: C.green });
  addText(slide, "冻结评测通过", { left: 816, top: 552, width: 220, height: 30 }, { fontSize: 19, color: C.muted });
  addText(slide, "离线 Proxy 与模拟数据，不等同于真实模型 A/B", { left: 816, top: 606, width: 360, height: 32 }, {
    fontSize: 17,
    color: C.amber,
    bold: true,
  });
  setNotes(
    slide,
    "评测分为任务成功率、工具路由准确率、答案正确性和调用效率。早期关键词 Router 在挑战集上只有 61.76%，加入别名、工具描述、Planner 和 Bad-case 回归后达到冻结集 100%。这里的 DirectLLMProxy 与 RAGOnlyProxy 是离线可复现基线，不冒充真实商业模型。",
    [
      "Local evaluation dashboard screenshot: docs/assets/evaluation-dashboard.png",
      "Experiment results: docs/experiment_results.md",
      "Current project summary: docs/project_summary.md",
    ],
  );
}

function buildClose(presentation) {
  const slide = presentation.slides.add();
  slide.background.fill = C.white;
  addHeader(slide, "完整工程闭环已验证，真实 Provider A/B 是下一项独立实验", 5);

  addText(slide, "工程证据", { left: 56, top: 148, width: 260, height: 34 }, { fontSize: 27, bold: true });
  addText(slide, "138", { left: 56, top: 214, width: 150, height: 62 }, { fontSize: 52, bold: true, color: C.teal });
  addText(slide, "tests passed", { left: 56, top: 278, width: 180, height: 28 }, { fontSize: 18, color: C.muted });
  addText(slide, "100/100 + 40/40", { left: 56, top: 338, width: 310, height: 48 }, { fontSize: 34, bold: true, color: C.blue });
  addText(slide, "PostgreSQL load / recovery", { left: 56, top: 392, width: 300, height: 28 }, { fontSize: 18, color: C.muted });
  addText(slide, "6/6", { left: 56, top: 452, width: 150, height: 52 }, { fontSize: 42, bold: true, color: C.green });
  addText(slide, "fault gates", { left: 56, top: 508, width: 180, height: 28 }, { fontSize: 18, color: C.muted });

  addRule(slide, 410, 146, 2, 444, C.faint);
  addText(slide, "受控边界", { left: 464, top: 148, width: 260, height: 34 }, { fontSize: 27, bold: true });
  addText(slide, "公开风格模拟数据\n不复制企业内部资产\n候选策略默认 inactive\nShadow + 全量回归 + 人审\n灰度发布与自动回滚", { left: 464, top: 218, width: 318, height: 254 }, {
    fontSize: 22,
    autoFit: "none",
  });
  addRect(slide, { left: 464, top: 500, width: 304, height: 74 }, C.amberLight);
  addText(slide, "真实 Provider A/B\n尚未执行", { left: 482, top: 512, width: 270, height: 50 }, {
    fontSize: 21,
    bold: true,
    color: C.amber,
    alignment: "center",
  });

  addRule(slide, 824, 146, 2, 444, C.faint);
  addText(slide, "可直接验收", { left: 878, top: 148, width: 280, height: 34 }, { fontSize: 27, bold: true });
  addText(slide, "GitHub Actions", { left: 878, top: 222, width: 280, height: 34 }, { fontSize: 25, bold: true, color: C.green });
  addText(slide, "Tests · Docker · PostgreSQL", { left: 878, top: 268, width: 310, height: 30 }, { fontSize: 18, color: C.muted });
  addText(slide, "Run 33314875879", { left: 878, top: 330, width: 300, height: 34 }, { fontSize: 23, bold: true, typeface: MONO });
  addText(slide, "github.com/Isoldelu/\nsoftware-engineering-agent", { left: 878, top: 410, width: 314, height: 80 }, {
    fontSize: 20,
    color: C.blue,
    bold: true,
    autoFit: "none",
  });
  addText(slide, "下一步：小预算 Provider A/B\n固定 12 条代表性 Query，显式记录成本与失败回退", { left: 878, top: 530, width: 326, height: 74 }, {
    fontSize: 18,
    color: C.muted,
  });
  addText(slide, "结论：这是一个有工具、有证据、有评测、可部署、可回滚的 AI4SE Agent。", { left: 56, top: 634, width: 1120, height: 34 }, {
    fontSize: 23,
    bold: true,
    color: C.teal,
    alignment: "center",
  });
  setNotes(
    slide,
    "最后用工程证据和诚实边界收口。当前 CI 已覆盖测试、Docker 和真实 PostgreSQL 多 Worker 路径；受控自进化不会自动修改源码或直接上线。还没有做的是付费真实 Provider A/B，这应作为预算明确后的独立实验，而不是阻塞现有项目交付。",
    [
      "GitHub Actions Run: https://github.com/Isoldelu/software-engineering-agent/actions/runs/33314875879",
      "Operational evidence: docs/step28-observability-disaster-recovery.md",
      "Public repository: https://github.com/Isoldelu/software-engineering-agent",
      "Project boundaries: docs/project-showcase.md",
    ],
  );
}

async function main() {
  await fs.mkdir(path.dirname(OUTPUT), { recursive: true });
  const presentation = Presentation.create({ slideSize: { width: W, height: H } });
  buildCover(presentation);
  buildArchitecture(presentation);
  await buildQueryEvidence(presentation);
  await buildEvaluation(presentation);
  buildClose(presentation);

  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(OUTPUT);
  process.stdout.write(`${OUTPUT}\n`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
