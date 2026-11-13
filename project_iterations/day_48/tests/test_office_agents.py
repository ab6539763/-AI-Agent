"""Day 48 单元测试：验证多 Agent 智能办公助手、6 大办公工具与 SQLite 断点审批恢复."""

import sys
from pathlib import Path

import pytest

DAY_DIR = Path(__file__).resolve().parent.parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    CalendarAgent,
    MailAgent,
    OfficeSupervisor,
    OfficeWorkspace,
    ResearchAgent,
    SQLiteCheckpointer,
    TaskStatus,
    create_default_tools,
)


def test_all_six_office_tools() -> None:
    """验证 6 大核心办公工具的正常执行与状态变更."""
    ws = OfficeWorkspace()
    tools = create_default_tools(ws)
    assert set(tools.keys()) == {
        "list_calendar",
        "create_meeting",
        "draft_email",
        "send_email",
        "search_company_docs",
        "web_search",
    }

    cal = tools["list_calendar"].invoke(date="2026-11-16")
    assert cal["count"] == 2

    created = tools["create_meeting"].invoke(
        title="架构同步会",
        date="2026-11-17",
        start_time="10:00",
        attendees=["张工", "陈默"],
    )
    assert created["status"] == "created"
    assert created["conflict_warning"] is False
    assert tools["list_calendar"].invoke(date="2026-11-17")["count"] == 1

    drafted = tools["draft_email"].invoke(
        to=["linxiao@zhishu.cn"],
        subject="测试草稿",
        body="草稿正文",
    )
    draft_id = drafted["draft"]["draft_id"]
    assert len(ws.email_drafts) == 1

    sent = tools["send_email"].invoke(
        to=["linxiao@zhishu.cn"],
        subject="测试发送",
        body="正式正文",
        draft_id=draft_id,
    )
    assert sent["status"] == "sent"
    assert len(ws.sent_emails) == 1
    assert ws.email_drafts[0]["status"] == "sent"

    docs = tools["search_company_docs"].invoke(query="Q4 AI 战略", top_k=2)
    assert docs["count"] >= 1
    assert any("战略" in d["title"] for d in docs["results"])

    web = tools["web_search"].invoke(query="SQLite 断点恢复", top_k=2)
    assert web["count"] >= 1


def test_collaborating_agents_and_supervisor_without_interrupts(tmp_path: Path) -> None:
    """验证 ResearchAgent / CalendarAgent / MailAgent 协同与只读/低危流程端到端完成."""
    db_path = tmp_path / "no_interrupt.db"
    supervisor = OfficeSupervisor(
        checkpointer=SQLiteCheckpointer(db_path),
        interrupt_before=set(),
    )
    assert isinstance(supervisor.agents["ResearchAgent"], ResearchAgent)
    assert isinstance(supervisor.agents["CalendarAgent"], CalendarAgent)
    assert isinstance(supervisor.agents["MailAgent"], MailAgent)

    res = supervisor.run(
        "请调研公司架构规范文档，查询当前日程，并草拟一封项目同步邮件",
        thread_id="t-low-risk",
    )
    assert res["status"] == TaskStatus.COMPLETED.value
    assert "ResearchAgent" in res["agent_outputs"]
    assert "CalendarAgent" in res["agent_outputs"]
    assert "MailAgent" in res["agent_outputs"]
    assert len(supervisor.workspace.email_drafts) == 1
    assert len(supervisor.workspace.sent_emails) == 0


def test_sqlite_interrupt_and_cross_instance_resume(tmp_path: Path) -> None:
    """验证高危操作中断挂起、SQLite 持久化及跨 Supervisor 实例恢复（含参数微调）."""
    db_path = tmp_path / "office_hitl.db"
    ws = OfficeWorkspace()

    sup1 = OfficeSupervisor(
        workspace=ws,
        checkpointer=SQLiteCheckpointer(db_path),
        interrupt_before={"create_meeting", "send_email"},
    )
    res1 = sup1.run(
        "请调研 Q4 战略文档，预约会议并发送邮件通知",
        thread_id="t-hitl-01",
    )
    assert res1["status"] == TaskStatus.INTERRUPTED.value
    assert res1["pending_action"]["tool_name"] == "create_meeting"
    assert len(ws.calendar_events) == 2  # 尚未写入新会议

    # 模拟进程重启：新建 Supervisor 实例共享同一 SQLite 文件
    sup2 = OfficeSupervisor(
        workspace=ws,
        checkpointer=SQLiteCheckpointer(db_path),
        interrupt_before={"create_meeting", "send_email"},
    )
    res2 = sup2.resume(
        "t-hitl-01",
        approved=True,
        modified_args={"start_time": "17:00"},
        feedback="改到下午五点",
    )
    assert res2["status"] == TaskStatus.INTERRUPTED.value
    assert res2["pending_action"]["tool_name"] == "send_email"
    assert len(ws.calendar_events) == 3
    assert ws.calendar_events[-1]["start_time"] == "17:00"
    assert len(ws.sent_emails) == 0  # 邮件尚未发送

    res3 = sup2.resume("t-hitl-01", approved=True, feedback="确认发送")
    assert res3["status"] == TaskStatus.COMPLETED.value
    assert len(ws.sent_emails) == 1
    assert "17:00" in ws.sent_emails[0]["body"]

    final_state = sup2.get_state("t-hitl-01")
    assert final_state is not None
    assert len(final_state.approval_history) == 2
    assert len(sup2.get_history("t-hitl-01")) >= 4


def test_interrupt_rejection_and_invalid_resume(tmp_path: Path) -> None:
    """验证人工拒绝高危操作时安全中止，且重复恢复或不存在的 thread_id 抛出 ValueError."""
    db_path = tmp_path / "reject.db"
    ws = OfficeWorkspace()
    supervisor = OfficeSupervisor(
        workspace=ws,
        checkpointer=SQLiteCheckpointer(db_path),
        interrupt_before={"send_email"},
    )

    res1 = supervisor.run("请发送邮件通知全员", thread_id="t-reject")
    assert res1["status"] == TaskStatus.INTERRUPTED.value
    assert len(ws.email_drafts) == 1
    assert len(ws.sent_emails) == 0

    res2 = supervisor.resume("t-reject", approved=False, feedback="收件人范围过大")
    assert res2["status"] == TaskStatus.REJECTED.value
    assert "收件人范围过大" in res2["final_response"]
    assert len(ws.sent_emails) == 0

    with pytest.raises(ValueError, match="无法执行审批恢复"):
        supervisor.resume("t-reject", approved=True)

    with pytest.raises(ValueError, match="未找到"):
        supervisor.resume("non-existent-thread", approved=True)
