"""Offline interview rehearsal plans with optional interactive timing."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from typing import Literal

Mode = Literal["90s", "standard", "evolution"]


@dataclass(frozen=True)
class Segment:
    title: str
    target_seconds: int
    script: str


@dataclass(frozen=True)
class RehearsalPlan:
    mode: Mode
    title: str
    target_seconds: int
    segments: tuple[Segment, ...]


PLANS: dict[Mode, RehearsalPlan] = {
    "90s": RehearsalPlan(
        mode="90s",
        title="90 秒项目总览",
        target_seconds=90,
        segments=(
            Segment(
                "定位",
                15,
                "这是一个基于公开风格模拟数据复现的 AI4SE Agent，不包含华为内部数据。",
            ),
            Segment(
                "架构",
                20,
                "Planner 组合五个领域工具，结果统一进入 Evidence、Citation、Verifier 和 Trace。",
            ),
            Segment(
                "Demo 与评测",
                25,
                "nginx 复合 Query 触发三个工具；冻结集 193/193，通过离线 Proxy 对比和 Bad-case 回归量化优化。",
            ),
            Segment(
                "受控自进化",
                20,
                "系统离线挖掘 9 个失败，生成三类配置候选，Shadow 修复 9 个且零回归，但自动激活被阻断。",
            ),
            Segment(
                "工程边界",
                10,
                "CI 已验证 150 项测试、Docker 和 PostgreSQL；真实 Provider A/B 尚未执行。",
            ),
        ),
    ),
    "standard": RehearsalPlan(
        mode="standard",
        title="3 分 30 秒标准面试讲解",
        target_seconds=210,
        segments=(
            Segment(
                "问题与定位",
                25,
                "研发资产分散在包、依赖、版本和文档中。我使用公开风格模拟数据构建个人复现项目，验证华为实习中接触的方法论，不复制内部数据。",
            ),
            Segment(
                "Agent 架构",
                40,
                "Query 先经过多轮 Context，再由 Planner 和 Router 生成单工具或 Hybrid Plan。五个工具处理 Package、Dependency、Version、Component 和 RAG，结果转成 Evidence 与 Citation，经确定性 Verifier 后生成可回放 Trace。",
            ),
            Segment(
                "复合任务 Demo",
                40,
                "以 nginx 版本变化和依赖为例，Planner 组合三个工具，返回三条 Evidence、三条 Citation，Verifier 与 Trace 均通过。多工具规划的价值是把复合问题拆成可验证子任务。",
            ),
            Segment(
                "评测优化",
                35,
                "关键词 Router 在挑战集上为 61.76%，加入别名、工具描述、Hybrid Planner 和 Bad-case 回归后，冻结集达到 100%。DirectLLMProxy 与 RAGOnlyProxy 是离线 Proxy，不是真实商业模型对比。",
            ),
            Segment(
                "受控自进化",
                40,
                "离线循环挖掘 9 个失败并聚成 Router、Alias、Retriever 三类根因，Shadow 与冻结回归修复 9 个且零回归。人工批准后由 Reviewed Bridge 创建灰度策略，但候选不能改源码或自行发布。",
            ),
            Segment(
                "工程证据与边界",
                30,
                "GitHub Actions Run 33354020784 验证 150 项测试、Docker 和真实 PostgreSQL 多 Worker 门禁。Evolution 候选已通过受审 Bridge 接入灰度与回滚；真实 Provider A/B 尚未执行。",
            ),
        ),
    ),
    "evolution": RehearsalPlan(
        mode="evolution",
        title="2 分 30 秒自进化专项回答",
        target_seconds=150,
        segments=(
            Segment(
                "定义",
                20,
                "我实现的是离线、配置级、受控自进化，不是模型自行改代码或无审核上线。",
            ),
            Segment(
                "失败发现",
                30,
                "OfflineFailureMiner 重跑标注 Agent 与 RAG 用例，识别 Router Miss、Entity Alias Miss 和 Retriever Rank Miss，并要求同类问题至少出现两次才形成根因簇。",
            ),
            Segment(
                "候选与验证",
                35,
                "系统只生成 Router Rule、Query Alias 和 Retriever Weights 三类配置候选，在隔离 Session 与 Trace 中执行关联用例和冻结回归；实验修复 9 个失败且零回归。",
            ),
            Segment(
                "安全门禁",
                30,
                "候选最高自动状态是 pending_review，自动激活接口固定拒绝。人工批准后仍需 admin 通过受审 Bridge，才能创建版本化灰度策略，并由监控决定提升或回滚。",
            ),
            Segment(
                "尚未实现",
                35,
                "尚未实现在线持续学习、模型微调、RL 或源码自修改；Reviewed Bridge 只发布白名单配置，不允许 Agent 自动审核、降低评测门槛或自行上线。",
            ),
        ),
    ),
}


REQUIRED_BOUNDARIES: dict[Mode, tuple[str, ...]] = {
    "90s": ("模拟数据", "离线 Proxy", "真实 Provider A/B 尚未执行"),
    "standard": ("不复制内部数据", "离线 Proxy", "不能改源码", "受审 Bridge"),
    "evolution": ("配置级", "pending_review", "自动激活", "尚未实现", "Reviewed Bridge"),
}


def get_plan(mode: Mode) -> RehearsalPlan:
    return PLANS[mode]


def validate_plan(plan: RehearsalPlan) -> list[str]:
    issues: list[str] = []
    if sum(item.target_seconds for item in plan.segments) != plan.target_seconds:
        issues.append("segment_duration_mismatch")
    if any(not item.title.strip() or not item.script.strip() for item in plan.segments):
        issues.append("empty_segment")
    combined = "\n".join(item.script for item in plan.segments)
    for phrase in REQUIRED_BOUNDARIES[plan.mode]:
        if phrase not in combined:
            issues.append(f"missing_boundary:{phrase}")
    return issues


def render_plan(plan: RehearsalPlan) -> str:
    lines = [f"{plan.title} | target={plan.target_seconds}s"]
    elapsed = 0
    for index, segment in enumerate(plan.segments, start=1):
        start = elapsed
        elapsed += segment.target_seconds
        lines.extend((
            "",
            f"[{index}] {segment.title} | {start:03d}-{elapsed:03d}s | target={segment.target_seconds}s",
            segment.script,
        ))
    return "\n".join(lines)


def run_interactive(plan: RehearsalPlan) -> dict[str, object]:
    results = []
    for segment in plan.segments:
        print(f"\n{segment.title} | target={segment.target_seconds}s")
        print(segment.script)
        input("按 Enter 开始本段，讲完后再次按 Enter。")
        started = time.perf_counter()
        input()
        actual = round(time.perf_counter() - started, 2)
        results.append({
            "title": segment.title,
            "target_seconds": segment.target_seconds,
            "actual_seconds": actual,
            "delta_seconds": round(actual - segment.target_seconds, 2),
        })
    return {
        "mode": plan.mode,
        "target_seconds": plan.target_seconds,
        "actual_seconds": round(sum(item["actual_seconds"] for item in results), 2),
        "segments": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=tuple(PLANS), default="standard")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    plan = get_plan(args.mode)
    issues = validate_plan(plan)
    if issues:
        print(json.dumps({"valid": False, "issues": issues}, ensure_ascii=False))
        return 1
    if args.interactive:
        print(json.dumps(run_interactive(plan), ensure_ascii=False, indent=2))
    elif args.as_json:
        print(json.dumps(asdict(plan), ensure_ascii=False, indent=2))
    else:
        print(render_plan(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
