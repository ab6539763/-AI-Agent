"""Day 49 核心模块：多 Agent 智能办公助手编排引擎与 SQLite HITL 检查点持久化 (v0.4.0-day49)."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    """返回标准 UTC ISO-8601 时间戳。"""
    return datetime.now(timezone.utc).isoformat()


class ThreadNotFoundError(KeyError):
    """当指定的 thread_id 在检查点存储中不存在时抛出。"""


class InvalidThreadStateError(ValueError):
    """当线程当前状态不允许执行 resume 等状态转换操作时抛出。"""


class HandoffStep(BaseModel):
    """多 Agent 协作流转轨迹中的单步记录。"""

    step: int
    from_agent: str
    to_agent: str
    action: str
    summary: str
    timestamp: str = Field(default_factory=_utc_now_iso)


class PendingAction(BaseModel):
    """触发 Human-in-the-Loop (HITL) 中断时的待审批高危动作载荷。"""

    action_id: str
    agent: str
    action_type: str
    risk_level: str = "high"
    title: str
    description: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ThreadState(BaseModel):
    """智能办公助手单次任务线程的完整状态快照。"""

    thread_id: str
    user_id: str = "default"
    task: str
    status: str  # completed | awaiting_approval | rejected
    handoff_trace: list[HandoffStep] = Field(default_factory=list)
    pending_action: PendingAction | None = None
    resolved_action: PendingAction | None = None
    final_output: str | None = None
    decision: str | None = None  # approved | rejected | None
    comment: str = ""
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)


class OfficeCheckpointer:
    """基于 SQLite 的多 Agent 线程状态检查点持久化器。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        if str(db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS office_threads (
                    thread_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    task TEXT NOT NULL,
                    status TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_office_threads_updated
                ON office_threads(updated_at DESC);
                """
            )

    def save(self, state: ThreadState) -> ThreadState:
        """保存或更新线程状态快照。"""
        state.updated_at = _utc_now_iso()
        state_json = state.model_dump_json()
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO office_threads (thread_id, user_id, task, status, state_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    status = excluded.status,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at;
                """,
                (
                    state.thread_id,
                    state.user_id,
                    state.task,
                    state.status,
                    state_json,
                    state.created_at,
                    state.updated_at,
                ),
            )
        return state

    def load(self, thread_id: str) -> ThreadState:
        """根据 thread_id 加载线程状态，不存在则抛出 ThreadNotFoundError。"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT state_json FROM office_threads WHERE thread_id = ?;",
                (thread_id,),
            ).fetchone()
        if row is None:
            raise ThreadNotFoundError(f"Thread '{thread_id}' not found")
        return ThreadState.model_validate_json(row["state_json"])

    def list_threads(self, limit: int = 30) -> list[ThreadState]:
        """按最近更新时间倒序列出线程状态。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT state_json FROM office_threads ORDER BY updated_at DESC LIMIT ?;",
                (limit,),
            ).fetchall()
        return [ThreadState.model_validate_json(r["state_json"]) for r in rows]


class OfficeOrchestrator:
    """多 Agent 智能办公编排器（Supervisor + 专职 Worker + HITL 中断/恢复）。"""

    def __init__(self, checkpointer: OfficeCheckpointer) -> None:
        self.checkpointer = checkpointer

    @staticmethod
    def _classify_task(task: str) -> str:
        """根据任务语义路由到对应的专职 Worker（高危动作将触发 HITL 审批）。"""
        lowered = task.lower()
        if any(k in lowered for k in ("发送", "群发", "email", "mail")) or (
            "邮件" in lowered and not any(q in lowered for q in ("查询", "检索", "制度"))
        ):
            return "email"
        if any(k in lowered for k in ("审批", "付款", "转账", "approve")) or (
            any(k in lowered for k in ("报销", "请假", "expense"))
            and not any(q in lowered for q in ("查询", "检索", "制度", "规范", "政策"))
        ):
            return "approval"
        if any(k in lowered for k in ("预订", "预约", "schedule")) or (
            any(k in lowered for k in ("会议", "日程", "meeting", "calendar"))
            and not any(q in lowered for q in ("查询", "检索", "制度", "规范", "纪要"))
        ):
            return "meeting"
        return "research"

    def run(
        self,
        task: str,
        thread_id: str | None = None,
        user_id: str = "default",
    ) -> ThreadState:
        """启动多 Agent 办公任务：低风险直接完成，高风险在执行前触发 HITL 中断。"""
        cleaned_task = task.strip()
        if not cleaned_task:
            raise ValueError("Task must not be empty")

        tid = thread_id or f"thread-{uuid.uuid4().hex[:12]}"
        route = self._classify_task(cleaned_task)
        trace: list[HandoffStep] = [
            HandoffStep(
                step=1,
                from_agent="user",
                to_agent="supervisor",
                action="receive_task",
                summary=f"接收办公指令：{cleaned_task}",
            )
        ]

        if route == "research":
            trace.append(
                HandoffStep(
                    step=2,
                    from_agent="supervisor",
                    to_agent="kb_researcher",
                    action="delegate_research",
                    summary="任务判定为只读检索/分析类，路由至知识库研究员（无需人工审批）。",
                )
            )
            trace.append(
                HandoffStep(
                    step=3,
                    from_agent="kb_researcher",
                    to_agent="supervisor",
                    action="return_findings",
                    summary="已完成内部知识库检索与结构化汇总。",
                )
            )
            trace.append(
                HandoffStep(
                    step=4,
                    from_agent="supervisor",
                    to_agent="user",
                    action="complete_task",
                    summary="多 Agent 协作完成，直接输出最终结果。",
                )
            )
            state = ThreadState(
                thread_id=tid,
                user_id=user_id,
                task=cleaned_task,
                status="completed",
                handoff_trace=trace,
                pending_action=None,
                final_output=(
                    f"【智能办公调研报告】\n"
                    f"针对您的请求「{cleaned_task}」，`kb_researcher` 已检索企业制度库并完成整理：\n"
                    f"1. 核心依据：星辰数科《2026 智能办公与差旅规范 v3.2》；\n"
                    f"2. 执行建议：本任务属于只读信息检索与摘要生成，不涉及外部发送或资金审批，已自动完成。"
                ),
            )
            return self.checkpointer.save(state)

        # 高风险任务：先由 kb_researcher 准备上下文，再交由目标执行 Agent，并在执行前触发 HITL 中断
        trace.append(
            HandoffStep(
                step=2,
                from_agent="supervisor",
                to_agent="kb_researcher",
                action="gather_context",
                summary="收集相关联系人、制度规范与业务上下文。",
            )
        )

        if route == "email":
            target_agent = "email_dispatcher"
            pending = PendingAction(
                action_id=f"act-{uuid.uuid4().hex[:10]}",
                agent=target_agent,
                action_type="send_email",
                risk_level="high",
                title="高风险动作审批：对外/全员发送邮件",
                description=f"准备执行邮件发送任务：「{cleaned_task}」。邮件发出后不可撤回，请人工确认收件人与正文内容。",
                payload={
                    "to": ["all-staff@xingchen.com"],
                    "subject": f"【办公助手代发】{cleaned_task[:32]}",
                    "body": f"各位同事好，\n\n根据指令「{cleaned_task}」整理通知如下，请查收。\n\n—— 智枢智能办公助手",
                },
            )
        elif route == "approval":
            target_agent = "finance_approver"
            pending = PendingAction(
                action_id=f"act-{uuid.uuid4().hex[:10]}",
                agent=target_agent,
                action_type="approve_expense",
                risk_level="high",
                title="高风险动作审批：财务报销/流程签批",
                description=f"准备执行审批流操作：「{cleaned_task}」。涉及预算扣减或考勤变更，需主管人工核准。",
                payload={
                    "request_type": "expense_or_leave",
                    "detail": cleaned_task,
                    "estimated_amount_cny": 2480.0,
                },
            )
        else:
            target_agent = "meeting_scheduler"
            pending = PendingAction(
                action_id=f"act-{uuid.uuid4().hex[:10]}",
                agent=target_agent,
                action_type="schedule_meeting",
                risk_level="medium",
                title="外部日程确认：预订会议室并发送日历邀请",
                description=f"准备创建会议日程并向参会人发送日历邀请：「{cleaned_task}」。",
                payload={
                    "room": "星辰大厦 18F-天枢会议室",
                    "time_slot": "明日 14:00 - 15:00",
                    "attendees": ["zhanggong@xingchen.com", "linxiao@xingchen.com"],
                    "topic": cleaned_task,
                },
            )

        trace.append(
            HandoffStep(
                step=3,
                from_agent="supervisor",
                to_agent=target_agent,
                action="prepare_action",
                summary=f"已由 {target_agent} 生成待执行载荷，检测到敏感/外部副作用操作，触发 HITL 中断。",
            )
        )
        trace.append(
            HandoffStep(
                step=4,
                from_agent=target_agent,
                to_agent="human_reviewer",
                action="interrupt_for_approval",
                summary=f"挂起线程 {tid}，等待人工审批（{pending.title}）。",
            )
        )

        state = ThreadState(
            thread_id=tid,
            user_id=user_id,
            task=cleaned_task,
            status="awaiting_approval",
            handoff_trace=trace,
            pending_action=pending,
            final_output=None,
        )
        return self.checkpointer.save(state)

    def resume(
        self,
        thread_id: str,
        approved: bool,
        comment: str = "",
        edited_payload: dict[str, Any] | None = None,
    ) -> ThreadState:
        """接收人工审批决策（批准或拒绝），从检查点恢复并完成或终止任务。"""
        state = self.checkpointer.load(thread_id)
        if state.status != "awaiting_approval" or state.pending_action is None:
            raise InvalidThreadStateError(
                f"Thread '{thread_id}' is in status '{state.status}', cannot resume"
            )

        pending = state.pending_action.model_copy(deep=True)
        if edited_payload:
            pending.payload.update(edited_payload)

        next_step = len(state.handoff_trace) + 1
        note = f"（备注：{comment}）" if comment.strip() else ""

        if approved:
            state.handoff_trace.append(
                HandoffStep(
                    step=next_step,
                    from_agent="human_reviewer",
                    to_agent=pending.agent,
                    action="approve",
                    summary=f"人工审批通过，允许 {pending.agent} 执行 {pending.action_type}{note}。",
                )
            )
            state.handoff_trace.append(
                HandoffStep(
                    step=next_step + 1,
                    from_agent=pending.agent,
                    to_agent="supervisor",
                    action="execute_and_report",
                    summary=f"{pending.agent} 已完成外部副作用操作并回传执行回执。",
                )
            )
            state.status = "completed"
            state.decision = "approved"
            state.comment = comment
            state.resolved_action = pending
            state.pending_action = None
            state.final_output = (
                f"✅ 【人工审批通过 · 任务已执行】\n"
                f"动作类型：{pending.action_type}（由 {pending.agent} 执行）\n"
                f"执行参数：{json.dumps(pending.payload, ensure_ascii=False)}\n"
                f"审批备注：{comment or '无'}\n"
                f"执行结果：操作已成功落盘并完成闭环通知。"
            )
        else:
            state.handoff_trace.append(
                HandoffStep(
                    step=next_step,
                    from_agent="human_reviewer",
                    to_agent="supervisor",
                    action="reject",
                    summary=f"人工审批拒绝，已拦截 {pending.agent} 的 {pending.action_type} 操作{note}。",
                )
            )
            state.status = "rejected"
            state.decision = "rejected"
            state.comment = comment
            state.resolved_action = pending
            state.pending_action = None
            state.final_output = (
                f"⛔ 【人工审批已拒绝 · 操作已安全拦截】\n"
                f"被拦截动作：{pending.title}（{pending.action_type}）\n"
                f"拒绝原因：{comment or '人工审核未通过'}\n"
                f"系统状态：未产生任何外部副作用，线程已安全归档。"
            )

        return self.checkpointer.save(state)
