from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_rehearsal_module():
    path = ROOT / "examples" / "interview_rehearsal.py"
    spec = importlib.util.spec_from_file_location("interview_rehearsal", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_step32_delivery_files_exist_and_cover_recording_modes():
    required = (
        "docs/evolution-capability-matrix.md",
        "docs/mock-interview-guide.md",
        "docs/recording-runbook.md",
        "docs/recording/Software-Agent-3m30s.srt",
        "examples/interview_rehearsal.py",
    )
    assert all((ROOT / path).is_file() for path in required)

    guide = (ROOT / "docs" / "mock-interview-guide.md").read_text(encoding="utf-8")
    runbook = (ROOT / "docs" / "recording-runbook.md").read_text(encoding="utf-8")
    assert "90 秒版本" in guide
    assert "3 分 30 秒版本" in guide
    assert "你的项目到底有没有自进化" in guide
    assert "00:00-00:25" in runbook
    assert "真实 Provider A/B 尚未执行" in runbook


def test_rehearsal_plans_match_target_durations_and_boundaries():
    rehearsal = _load_rehearsal_module()
    expected = {"90s": 90, "standard": 210, "evolution": 150}

    for mode, seconds in expected.items():
        plan = rehearsal.get_plan(mode)
        assert plan.target_seconds == seconds
        assert sum(item.target_seconds for item in plan.segments) == seconds
        assert rehearsal.validate_plan(plan) == []
        rendered = rehearsal.render_plan(plan)
        assert f"target={seconds}s" in rendered


def test_evolution_matrix_distinguishes_controlled_loop_from_autonomy():
    matrix = (ROOT / "docs" / "evolution-capability-matrix.md").read_text(
        encoding="utf-8"
    )
    assert "已经实现离线、配置级、受控自进化" in matrix
    assert "9 个失败" in matrix
    assert "零回归" in matrix
    assert "Evolution Candidate 与可发布 Policy Candidate 使用不同模型" in matrix
    assert "在线持续学习" in matrix
    assert "未实现" in matrix
    assert "源码自修改" in matrix


def test_recording_subtitles_end_at_standard_plan_duration():
    subtitles = (
        ROOT / "docs" / "recording" / "Software-Agent-3m30s.srt"
    ).read_text(encoding="utf-8")
    assert subtitles.count("-->") == 6
    assert "00:03:30,000" in subtitles
    assert "134 项测试" in subtitles
    assert "自动激活" in subtitles
