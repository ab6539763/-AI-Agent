"""Day 70 结业模块单元测试：覆盖六阶段完整性、70天跨度校验、前沿趋势过滤、结业证书与路线图导出。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.graduation_summary import (
    ZHISHU_STAGE_MILESTONES,
    StageMilestone,
    TrendTracker,
    generate_career_roadmap,
    generate_graduation_certificate,
    render_evolution_summary,
    validate_curriculum_span,
)


def test_six_stages_completeness_and_version_tags() -> None:
    """验证 6 个阶段里程碑完整且版本标签覆盖 v0.1.0 ~ v1.0.0。"""
    assert len(ZHISHU_STAGE_MILESTONES) == 6
    versions = [s.version_tag for s in ZHISHU_STAGE_MILESTONES]
    assert versions == ["v0.1.0", "v0.2.0", "v0.3.0", "v0.4.0", "v0.5.0", "v1.0.0"]
    for stage in ZHISHU_STAGE_MILESTONES:
        assert stage.title
        assert stage.platform_deliverable
        assert len(stage.core_topics) >= 3


def test_70_day_span_check_contiguous_and_exact() -> None:
    """验证 70 天课程跨度从 Day 01 到 Day 70 连续无断档，且能拦截异常跨度。"""
    span = validate_curriculum_span(ZHISHU_STAGE_MILESTONES)
    assert span["valid"] is True
    assert span["total_stages"] == 6
    assert span["start_day"] == 1
    assert span["end_day"] == 70
    assert span["total_days"] == 70

    summary_md = render_evolution_summary(ZHISHU_STAGE_MILESTONES)
    assert "Day 01 ~ Day 70" in summary_md
    assert "`v1.0.0`" in summary_md

    broken = list(ZHISHU_STAGE_MILESTONES)
    broken[-1] = StageMilestone(
        stage_number=6,
        stage_code="stage_06_capstone_and_career",
        title="第六阶段",
        day_start=58,
        day_end=69,
        version_tag="v1.0.0",
        core_topics=("a", "b", "c"),
        platform_deliverable="d",
        key_metrics="m",
    )
    with pytest.raises(ValueError, match="70 天"):
        validate_curriculum_span(broken)


def test_trend_tracker_covers_five_frontiers_and_filters() -> None:
    """验证 TrendTracker 覆盖 5 大前沿方向并支持类别、成熟度与关键词过滤。"""
    tracker = TrendTracker()
    all_trends = tracker.list_trends()
    assert len(all_trends) == 5

    categories = {t.category for t in all_trends}
    assert categories == {"reasoning", "protocol", "multimodal", "voice", "edge"}

    assert len(tracker.filter_by_category("protocol")) == 1
    assert tracker.filter_by_category("protocol")[0].trend_id == "mcp_agent_protocols"
    assert len(tracker.filter_by_maturity("production")) == 2
    assert any("DeepSeek-R1" in t.key_technologies or "o1 / o3" in t.key_technologies for t in tracker.search("o1"))

    md = tracker.summarize_markdown()
    assert "MCP" in md and "Edge" in md


def test_generate_graduation_certificate() -> None:
    """验证结业电子证书包含学员姓名、70天完成度、认证方向与版本主线。"""
    cert = generate_graduation_certificate(
        learner_name="林小满",
        completion_date="2026-11-13",
        track="RAG Engineer",
        completed_days=70,
    )
    assert "林小满" in cert
    assert "RAG Engineer" in cert
    assert "70/70 天" in cert
    assert "v0.1.0 -> v1.0.0" in cert
    assert "2026-11-13" in cert

    with pytest.raises(ValueError):
        generate_graduation_certificate(learner_name="   ")


def test_generate_career_roadmap_markdown_export() -> None:
    """验证 30/60/90 天职业发展路线图 Markdown 导出结构与岗位定制内容。"""
    roadmap = generate_career_roadmap(
        target_role="Agent Engineer",
        current_level="Junior -> Mid-level",
        learner_name="陈默",
    )
    assert "# 结业后 30 / 60 / 90 天职业发展路线图（陈默 · Agent Engineer）" in roadmap
    assert "## Day 1 - Day 30" in roadmap
    assert "## Day 31 - Day 60" in roadmap
    assert "## Day 61 - Day 90" in roadmap
    assert "MCP Server" in roadmap
    assert "- [ ]" in roadmap

    with pytest.raises(ValueError):
        generate_career_roadmap(target_role="Unknown Role")
