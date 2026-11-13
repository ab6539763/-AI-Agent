"""Day 61 单元测试：多工具协同、SQLite 持久化记忆、PII 脱敏与 HITL 审批中断/恢复."""

import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    ApprovalStatus,
    CapstoneAgentOrchestrator,
    ComplianceGuard,
    FinancialMetricsInput,
    FinancialRatioTool,
    RAGSearchTool,
)


def _sample_high_risk_metrics() -> FinancialMetricsInput:
    return FinancialMetricsInput(
        company_name="星辰制造科技",
        period="2026Q3",
        revenue=10000.0,
        net_profit=200.0,
        total_assets=20000.0,
        total_liabilities=16500.0,
        shareholders_equity=3500.0,
        current_assets=4000.0,
        current_liabilities=4500.0,
        gross_profit=2800.0,
    )


def _sample_healthy_metrics() -> FinancialMetricsInput:
    return FinancialMetricsInput(
        company_name="星辰云服务",
        period="2026Q3",
        revenue=15000.0,
        net_profit=2400.0,
        total_assets=20000.0,
        total_liabilities=7000.0,
        shareholders_equity=13000.0,
        current_assets=9000.0,
        current_liabilities=4000.0,
        gross_profit=9000.0,
    )


def test_financial_ratio_tool_calculation_and_validation() -> None:
    """财务比率工具应准确计算各项比率并识别高风险信号，同时拦截非法输入."""
    tool = FinancialRatioTool()
    high_risk = tool.calculate(_sample_high_risk_metrics())
    assert high_risk.roe_pct == 5.71
    assert high_risk.net_profit_margin_pct == 2.0
    assert high_risk.gross_margin_pct == 28.0
    assert high_risk.debt_to_asset_ratio_pct == 82.5
    assert high_risk.current_ratio == 0.89
    assert high_risk.risk_level == "HIGH"
    assert len(high_risk.risk_flags) >= 2

    healthy = tool.calculate(_sample_healthy_metrics())
    assert healthy.risk_level == "LOW"
    assert healthy.risk_flags == []

    bad_metrics = FinancialMetricsInput(
        company_name="异常测试",
        period="2026Q3",
        revenue=0.0,
        net_profit=10.0,
        total_assets=100.0,
        total_liabilities=50.0,
        shareholders_equity=50.0,
        current_assets=20.0,
        current_liabilities=10.0,
    )
    with pytest.raises(ValueError, match="revenue"):
        tool.calculate(bad_metrics)


def test_rag_search_tool_ranking() -> None:
    """RAG 检索工具应能按相关性返回企业风控与合规文档."""
    rag = RAGSearchTool()
    hits = rag.search("资产负债率 高杠杆 流动性 流动比率", top_k=2)
    assert len(hits) >= 1
    assert hits[0].doc_id == "DOC-RISK-001"
    assert hits[0].score > 0

    assert rag.search("", top_k=2) == []


def test_compliance_guard_pii_redaction() -> None:
    """合规脱敏网关应自动脱敏手机号、身份证、银行卡、邮箱与 API Key."""
    guard = ComplianceGuard()
    raw = (
        "联系人张三，手机 13800138000，身份证 11010519900101123X，"
        "邮箱 zhangsan@xingchen.ai，卡号 6222 0210 0111 2222 333，密钥 sk-prod9988776655。"
    )
    sanitized, counts = guard.redact(raw)
    assert "13800138000" not in sanitized
    assert "11010519900101123X" not in sanitized
    assert "zhangsan@xingchen.ai" not in sanitized
    assert "sk-prod9988776655" not in sanitized
    assert "[REDACTED_PHONE]" in sanitized
    assert "[REDACTED_ID_CARD]" in sanitized
    assert "[REDACTED_EMAIL]" in sanitized
    assert "[REDACTED_API_KEY]" in sanitized
    assert counts["phone"] == 1
    assert counts["id_card"] == 1
    assert counts["email"] == 1
    assert counts["api_key"] == 1


def test_sqlite_multi_turn_memory_persistence_and_isolation(tmp_path: Path) -> None:
    """SQLite 多轮记忆应在编排器重启后持久保留，且不同 session 严格隔离."""
    db_path = tmp_path / "memory.db"
    agent1 = CapstoneAgentOrchestrator(db_path=db_path)

    res1 = agent1.run(
        session_id="sess-alpha",
        user_query="请查询高管报告 HITL 审批规范，联系邮箱 audit@xingchen.ai。",
    )
    assert res1.status == ApprovalStatus.COMPLETED
    assert res1.redaction_counts.get("email") == 1

    # 模拟服务重启，使用新的 Orchestrator 实例读取同一 SQLite
    agent2 = CapstoneAgentOrchestrator(db_path=db_path)
    alpha_history = agent2.memory.get_history("sess-alpha")
    assert len(alpha_history) == 2
    assert "audit@xingchen.ai" not in alpha_history[0]["content"]
    assert "[REDACTED_EMAIL]" in alpha_history[0]["content"]

    # 第二轮对话应感知前序上下文
    res2 = agent2.run(
        session_id="sess-alpha",
        user_query="再结合星辰云服务 Q3 财报做一次常规分析。",
        financial_metrics=_sample_healthy_metrics(),
    )
    assert "2 条历史上下文" in res2.reply
    assert len(agent2.memory.get_history("sess-alpha")) == 4
    assert agent2.memory.get_history("sess-beta") == []


def test_hitl_interrupt_and_approve_publish_flow(tmp_path: Path) -> None:
    """发布高管风险报告必须先触发 HITL 中断，审批通过后才可正式发布并落库."""
    db_path = tmp_path / "hitl_approve.db"
    agent = CapstoneAgentOrchestrator(db_path=db_path)

    pause_res = agent.run(
        session_id="sess-report-1",
        user_query="请生成星辰制造科技 2026Q3 风险报告并发布，联系人 13912345678。",
        financial_metrics=_sample_high_risk_metrics(),
        require_report_publish=True,
    )
    assert pause_res.status == ApprovalStatus.PENDING_APPROVAL
    assert pause_res.approval_id is not None
    assert pause_res.financial_result is not None
    assert pause_res.financial_result.risk_level == "HIGH"
    # 中断期间严禁提前发布
    assert agent.memory.list_published_reports("sess-report-1") == []

    # 跨实例恢复审批并放行
    resumed_agent = CapstoneAgentOrchestrator(db_path=db_path)
    approve_res = resumed_agent.resume(
        approval_id=pause_res.approval_id,
        approved=True,
        reviewer="财务总监-王芳",
        comment="高杠杆风险已核实，准予发布。",
    )
    assert approve_res.status == ApprovalStatus.APPROVED
    assert approve_res.published_report is not None
    assert "13912345678" not in approve_res.published_report.content
    assert "[REDACTED_PHONE]" in approve_res.published_report.content

    published = resumed_agent.memory.list_published_reports("sess-report-1")
    assert len(published) == 1
    assert published[0].published_by == "财务总监-王芳"

    # 禁止重复审批同一个检查点
    with pytest.raises(ValueError, match="无法重复审批"):
        resumed_agent.resume(
            approval_id=pause_res.approval_id,
            approved=True,
            reviewer="财务总监-王芳",
        )


def test_hitl_interrupt_and_reject_flow(tmp_path: Path) -> None:
    """人工驳回后，检查点应更新为 REJECTED 且不得生成已发布报告."""
    db_path = tmp_path / "hitl_reject.db"
    agent = CapstoneAgentOrchestrator(db_path=db_path)

    pause_res = agent.run(
        session_id="sess-report-2",
        user_query="请求发布综合风控报告。",
        require_report_publish=True,
    )
    assert pause_res.approval_id is not None

    reject_res = agent.resume(
        approval_id=pause_res.approval_id,
        approved=False,
        reviewer="法务合规-赵敏",
        comment="需补充关联交易说明后再行提交。",
    )
    assert reject_res.status == ApprovalStatus.REJECTED
    assert reject_res.published_report is None
    assert agent.memory.list_published_reports("sess-report-2") == []

    cp = agent.memory.get_checkpoint(pause_res.approval_id)
    assert cp is not None
    assert cp.status == ApprovalStatus.REJECTED
    assert cp.reviewer == "法务合规-赵敏"
