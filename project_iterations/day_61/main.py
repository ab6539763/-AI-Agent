"""Day 61 平台启动入口：毕业设计开发日 3 —— 多工具协同、持久化记忆与 HITL 审批演示 (v1.0.0-day61)."""

import sys
import tempfile
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import CapstoneAgentOrchestrator, FinancialMetricsInput


def main() -> None:
    """演示多工具协同、PII 脱敏、SQLite 多轮记忆与 HITL 中断/恢复全流程."""
    print("=" * 76)
    print("🚀 智枢企业级智能体平台 v1.0.0-day61 · 毕业设计开发日 3 演示")
    print("=" * 76)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "zhishu_capstone.db"
        agent = CapstoneAgentOrchestrator(db_path=db_path)
        session_id = "demo-exec-2026q3"

        # Turn 1: 普通多轮问询（含敏感信息脱敏）
        turn1 = agent.run(
            session_id=session_id,
            user_query="请先帮我检索企业高杠杆与流动性风控指引，联系人张总手机 13800138000。",
        )
        print(f"\n[Turn 1] 状态: {turn1.status.value}")
        print(f"  脱敏统计: {turn1.redaction_counts}")
        print(f"  回复: {turn1.reply}")

        # Turn 2: 结合财报数据进行多工具协同并请求发布高管风险报告 -> 触发 HITL 中断
        metrics = FinancialMetricsInput(
            company_name="星辰制造科技",
            period="2026Q3",
            revenue=12000.0,
            net_profit=480.0,
            total_assets=25000.0,
            total_liabilities=19000.0,
            shareholders_equity=6000.0,
            current_assets=5200.0,
            current_liabilities=4800.0,
            gross_profit=3600.0,
        )
        turn2 = agent.run(
            session_id=session_id,
            user_query="基于 2026Q3 财报生成并发布高管风险评估报告，抄送 risk@xingchen.ai。",
            financial_metrics=metrics,
            require_report_publish=True,
        )
        print(f"\n[Turn 2] 状态: {turn2.status.value} | approval_id={turn2.approval_id}")
        print(f"  回复: {turn2.reply}")

        # 模拟进程重启：重新实例化 Orchestrator 连接同一 SQLite，完成人工审批恢复
        resumed_agent = CapstoneAgentOrchestrator(db_path=db_path)
        assert turn2.approval_id is not None
        turn3 = resumed_agent.resume(
            approval_id=turn2.approval_id,
            approved=True,
            reviewer="风控总监-李明",
            comment="指标口径核验无误，同意发布高管风险预警报告。",
        )
        print(f"\n[Turn 3 - HITL Resume] 状态: {turn3.status.value}")
        print(f"  回复: {turn3.reply}")
        if turn3.published_report:
            print(f"  已归档报告 ID: {turn3.published_report.report_id}")
            print(f"  会话历史消息总数: {len(resumed_agent.memory.get_history(session_id))}")


if __name__ == "__main__":
    main()
