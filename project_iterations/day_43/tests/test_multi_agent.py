"""Day 43 单元测试：Supervisor 模式多智能体协作、交接追踪与 max_rounds 熔断."""

import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parents[1]
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    FINISH,
    AgentWorker,
    AnalystAgent,
    ResearcherAgent,
    SupervisorOrchestrator,
    WorkerResult,
    WriterAgent,
)


def test_default_supervisor_workflow_and_handoffs() -> None:
    """验证默认 Supervisor 路由顺序 (Researcher -> Analyst -> Writer) 与研报生成."""
    orchestrator = SupervisorOrchestrator(max_rounds=6)
    result = orchestrator.run("RAG 与 Multi-Agent 融合架构")

    assert result.status == "completed"
    assert result.rounds_used == 3
    assert [h.to_agent for h in result.agent_handoffs] == [
        "researcher",
        "analyst",
        "writer",
    ]
    assert all(h.from_agent == "supervisor" for h in result.agent_handoffs)
    assert "RAG 与 Multi-Agent 融合架构" in result.final_report
    assert "背景与核心事实" in result.final_report
    assert "深度分析与关键洞察" in result.final_report


def test_custom_workers_context_propagation() -> None:
    """验证 Researcher -> Analyst -> Writer 共享上下文的数据透传与自定义回调."""
    researcher = ResearcherAgent(
        search_fn=lambda topic, ctx: [f"{topic} 指标 A 提升 35%", f"{topic} 延迟降低 20%"]
    )
    analyst = AnalystAgent(
        analyze_fn=lambda topic, ctx: {
            "insights": [f"基于 {len(ctx['findings'])} 条数据得出正向 ROI"],
            "risks": ["需关注并发限流"],
            "metrics": {"findings_count": len(ctx["findings"]), "roi_score": 9.2},
        }
    )
    writer = WriterAgent()

    orchestrator = SupervisorOrchestrator(
        workers=[researcher, analyst, writer],
        max_rounds=5,
    )
    result = orchestrator.run("智枢知识库升级")

    assert result.status == "completed"
    assert result.shared_context["metrics"]["roi_score"] == 9.2
    assert "指标 A 提升 35%" in result.final_report
    assert "正向 ROI" in result.final_report


def test_max_rounds_prevents_infinite_handoff_loop() -> None:
    """验证当自定义路由发生死循环时，max_rounds 能强制熔断并记录完整 handoffs."""

    def cyclic_router(ctx, handoffs, available):
        # 故意在 researcher 和 analyst 之间无限乒乓切换
        next_target = "analyst" if len(handoffs) % 2 == 1 else "researcher"
        return next_target, f"第 {len(handoffs) + 1} 轮循环调研"

    orchestrator = SupervisorOrchestrator(max_rounds=4, router_fn=cyclic_router)
    result = orchestrator.run("死循环熔断测试")

    assert result.status == "max_rounds_reached"
    assert result.rounds_used == 4
    assert len(result.agent_handoffs) == 4
    assert [h.to_agent for h in result.agent_handoffs] == [
        "researcher",
        "analyst",
        "researcher",
        "analyst",
    ]
    assert "阶段性汇总报告" in result.final_report


def test_invalid_max_rounds_and_unknown_worker_errors() -> None:
    """验证非法 max_rounds 与未注册 Worker 路由的边界异常检查."""
    with pytest.raises(ValueError, match="max_rounds"):
        SupervisorOrchestrator(max_rounds=0)

    orchestrator = SupervisorOrchestrator(
        max_rounds=2,
        router_fn=lambda ctx, h, avail: ("non_existent_agent", "do something"),
    )
    with pytest.raises(KeyError, match="non_existent_agent"):
        orchestrator.run("异常路由测试")


def test_extensible_reviewer_agent_registration() -> None:
    """验证通过继承 AgentWorker 扩展 ReviewerAgent 并接入自定义 Supervisor 路由."""

    class ReviewerAgent(AgentWorker):
        def __init__(self) -> None:
            super().__init__(
                name="reviewer",
                role="Quality Reviewer",
                description="审核研报完整性与格式规范",
            )

        def execute(self, task: str, context: dict) -> WorkerResult:
            report = context.get("report", "")
            approved = "核心事实" in report and "关键洞察" in report
            return WorkerResult(
                agent_name=self.name,
                role=self.role,
                output=f"审稿结果: {'PASS' if approved else 'REJECT'}",
                artifacts={"review_approved": approved},
            )

    def four_stage_router(ctx, handoffs, available):
        if "findings" not in ctx:
            return "researcher", "收集背景资料"
        if "insights" not in ctx:
            return "analyst", "分析数据洞察"
        if "report" not in ctx:
            return "writer", "撰写研报初稿"
        if "review_approved" not in ctx:
            return "reviewer", "质量审核"
        return FINISH, "审核通过"

    orchestrator = SupervisorOrchestrator(
        workers=[ResearcherAgent(), AnalystAgent(), WriterAgent(), ReviewerAgent()],
        max_rounds=6,
        router_fn=four_stage_router,
    )
    result = orchestrator.run("可扩展多智能体评审流")

    assert result.status == "completed"
    assert result.rounds_used == 4
    assert [h.to_agent for h in result.agent_handoffs] == [
        "researcher",
        "analyst",
        "writer",
        "reviewer",
    ]
    assert result.shared_context["review_approved"] is True
