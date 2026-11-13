"""Day 48 核心实现：多 Agent 智能办公助手（核心编排、6 大办公工具与 SQLite 断点恢复）。

包含：
- OfficeWorkspace & 6 大办公工具：list_calendar, create_meeting, draft_email, send_email,
  search_company_docs, web_search
- SQLiteCheckpointer：基于 SQLite 的状态持久化与断点恢复（支持 interrupt_before 高危操作审批）
- 3 大协同专业 Agent：ResearchAgent, CalendarAgent, MailAgent
- OfficeSupervisor：任务规划、多 Agent 路由调度、中断挂起与人工审批恢复（HITL）
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStatus(str, Enum):
    """多 Agent 办公任务执行状态."""

    PENDING = "pending"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class PendingAction:
    """高危工具调用挂起等待人工审批的动作描述."""

    action_id: str
    agent_name: str
    tool_name: str
    arguments: dict[str, Any]
    reason: str
    risk_level: str = "high"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentStepResult:
    """单个 Agent 执行一步的结果."""

    agent_name: str
    summary: str
    output: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    interrupted: bool = False
    pending_action: PendingAction | None = None


@dataclass
class OfficeState:
    """多 Agent 智能办公助手的全局共享状态（可序列化至 SQLite）."""

    thread_id: str
    user_request: str
    status: str = TaskStatus.PENDING.value
    plan: list[dict[str, Any]] = field(default_factory=list)
    current_step_index: int = 0
    agent_outputs: dict[str, Any] = field(default_factory=dict)
    tool_history: list[dict[str, Any]] = field(default_factory=list)
    pending_action: dict[str, Any] | None = None
    approval_history: list[dict[str, Any]] = field(default_factory=list)
    final_response: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OfficeState:
        return cls(
            thread_id=data["thread_id"],
            user_request=data["user_request"],
            status=data.get("status", TaskStatus.PENDING.value),
            plan=list(data.get("plan", [])),
            current_step_index=int(data.get("current_step_index", 0)),
            agent_outputs=dict(data.get("agent_outputs", {})),
            tool_history=list(data.get("tool_history", [])),
            pending_action=data.get("pending_action"),
            approval_history=list(data.get("approval_history", [])),
            final_response=data.get("final_response", ""),
            error=data.get("error"),
        )


@dataclass
class OfficeTool:
    """办公工具封装."""

    name: str
    description: str
    risk_level: str  # "low" | "high"
    fn: Callable[..., dict[str, Any]]

    def invoke(self, **kwargs: Any) -> dict[str, Any]:
        return self.fn(**kwargs)


class OfficeWorkspace:
    """模拟企业办公环境数据底座（日程、邮件草稿/已发送、企业文档库与联网搜索索引）."""

    def __init__(self) -> None:
        self.calendar_events: list[dict[str, Any]] = [
            {
                "meeting_id": "MTG-001",
                "title": "智枢平台研发晨会",
                "date": "2026-11-16",
                "start_time": "09:30",
                "duration_min": 30,
                "attendees": ["张工", "陈默", "李婷"],
            },
            {
                "meeting_id": "MTG-002",
                "title": "Q4 架构评审会",
                "date": "2026-11-16",
                "start_time": "14:00",
                "duration_min": 60,
                "attendees": ["张工", "林晓", "王总监"],
            },
        ]
        self.email_drafts: list[dict[str, Any]] = []
        self.sent_emails: list[dict[str, Any]] = []
        self.company_docs: list[dict[str, Any]] = [
            {
                "doc_id": "DOC-101",
                "title": "智枢平台 v0.4.0 多 Agent 办公助手架构规范",
                "department": "AI 平台研发部",
                "content": (
                    "智枢智能办公助手采用 Supervisor 协同架构，协调 ResearchAgent、"
                    "CalendarAgent 与 MailAgent。所有对外发送邮件(send_email)和创建正式会议"
                    "(create_meeting)必须经过 SQLite 断点持久化与人工审批(HITL)。"
                ),
            },
            {
                "doc_id": "DOC-102",
                "title": "星辰数科 Q4 AI 战略与预算规划",
                "department": "战略规划部",
                "content": (
                    "2026 年 Q4 重点推进企业级多智能体办公自动化落地，目标将周会纪要、"
                    "跨部门日程协调与行业竞品调研耗时降低 60%，预算重点向安全护栏与可观测性倾斜。"
                ),
            },
            {
                "doc_id": "DOC-103",
                "title": "企业差旅与会议审批制度（2026 修订版）",
                "department": "行政与财务部",
                "content": (
                    "跨部门正式会议需提前 24 小时发送日程邀请并同步会议议程；"
                    "对外发送合作邮件需经部门负责人确认收件人列表与核心承诺条款。"
                ),
            },
        ]
        self.web_index: list[dict[str, Any]] = [
            {
                "url": "https://docs.zhishu-ai.example.com/multi-agent-hitl",
                "title": "Multi-Agent Supervisor 与 Human-in-the-Loop 最佳实践",
                "snippet": (
                    "在企业办公场景中，使用 interrupt_before 在高危工具执行前挂起状态并写入 "
                    "SQLite Checkpointer，可实现零丢失的人工审批与参数修订恢复。"
                ),
            },
            {
                "url": "https://industry.example.com/2026-ai-office-benchmark",
                "title": "2026 企业智能办公助手行业基准报告",
                "snippet": (
                    "主流企业智能办公平台普遍集成日程管理、邮件协同与知识库 RAG 检索三大能力，"
                    "其中高危操作人工确认率达到 98% 以上。"
                ),
            },
            {
                "url": "https://engineering.example.com/langgraph-checkpoint-sqlite",
                "title": "基于 SQLite 的长程智能体断点恢复设计",
                "snippet": (
                    "通过 thread_id 隔离会话上下文，每次状态变更保存 JSON 快照，支持审批通过、"
                    "参数修改后继续执行以及拒绝回滚。"
                ),
            },
        ]


def create_default_tools(workspace: OfficeWorkspace) -> dict[str, OfficeTool]:
    """基于 OfficeWorkspace 创建 6 个标准办公工具."""

    def list_calendar(date: str | None = None) -> dict[str, Any]:
        events = workspace.calendar_events
        if date:
            events = [ev for ev in events if ev.get("date") == date]
        return {
            "count": len(events),
            "date_filter": date,
            "events": [dict(ev) for ev in events],
        }

    def create_meeting(
        title: str,
        date: str,
        start_time: str,
        attendees: list[str],
        duration_min: int = 60,
    ) -> dict[str, Any]:
        conflict = any(
            ev["date"] == date and ev["start_time"] == start_time
            for ev in workspace.calendar_events
        )
        meeting_id = f"MTG-{len(workspace.calendar_events) + 1:03d}"
        event = {
            "meeting_id": meeting_id,
            "title": title,
            "date": date,
            "start_time": start_time,
            "duration_min": duration_min,
            "attendees": list(attendees),
        }
        workspace.calendar_events.append(event)
        return {
            "status": "created",
            "conflict_warning": conflict,
            "meeting": event,
        }

    def draft_email(to: list[str], subject: str, body: str) -> dict[str, Any]:
        draft_id = f"DRF-{len(workspace.email_drafts) + 1:03d}"
        draft = {
            "draft_id": draft_id,
            "to": list(to),
            "subject": subject,
            "body": body,
            "status": "draft",
            "created_at": _utc_now_iso(),
        }
        workspace.email_drafts.append(draft)
        return {"status": "drafted", "draft": draft}

    def send_email(
        to: list[str],
        subject: str,
        body: str,
        draft_id: str | None = None,
    ) -> dict[str, Any]:
        if not to:
            raise ValueError("send_email 收件人列表不能为空")
        email_id = f"MSG-{len(workspace.sent_emails) + 1:03d}"
        record = {
            "email_id": email_id,
            "draft_id": draft_id,
            "to": list(to),
            "subject": subject,
            "body": body,
            "status": "sent",
            "sent_at": _utc_now_iso(),
        }
        workspace.sent_emails.append(record)
        if draft_id:
            for d in workspace.email_drafts:
                if d["draft_id"] == draft_id:
                    d["status"] = "sent"
        return {"status": "sent", "email": record}

    def _score_text(query: str, text: str) -> int:
        tokens = [tok.strip().lower() for tok in query.replace("，", " ").replace(",", " ").split() if tok.strip()]
        lowered = text.lower()
        score = sum(1 for tok in tokens if tok in lowered)
        # 额外支持中文连续子串匹配
        if not tokens or score == 0:
            for ch_len in (4, 3, 2):
                for idx in range(max(0, len(query) - ch_len + 1)):
                    sub = query[idx : idx + ch_len].strip().lower()
                    if sub and sub in lowered:
                        score += 1
        return score

    def search_company_docs(query: str, top_k: int = 3) -> dict[str, Any]:
        scored = []
        for doc in workspace.company_docs:
            haystack = f"{doc['title']} {doc['department']} {doc['content']}"
            s = _score_text(query, haystack)
            scored.append((s, doc))
        scored.sort(key=lambda item: item[0], reverse=True)
        hits = [dict(doc, score=score) for score, doc in scored[:top_k] if score > 0]
        if not hits and workspace.company_docs:
            hits = [dict(workspace.company_docs[0], score=0)]
        return {"query": query, "count": len(hits), "results": hits}

    def web_search(query: str, top_k: int = 3) -> dict[str, Any]:
        scored = []
        for page in workspace.web_index:
            haystack = f"{page['title']} {page['snippet']}"
            s = _score_text(query, haystack)
            scored.append((s, page))
        scored.sort(key=lambda item: item[0], reverse=True)
        hits = [dict(page, score=score) for score, page in scored[:top_k] if score > 0]
        if not hits and workspace.web_index:
            hits = [dict(workspace.web_index[0], score=0)]
        return {"query": query, "count": len(hits), "results": hits}

    return {
        "list_calendar": OfficeTool(
            name="list_calendar",
            description="查询指定日期或全部企业日程安排",
            risk_level="low",
            fn=list_calendar,
        ),
        "create_meeting": OfficeTool(
            name="create_meeting",
            description="创建企业会议日程（高危写操作，默认需人工审批）",
            risk_level="high",
            fn=create_meeting,
        ),
        "draft_email": OfficeTool(
            name="draft_email",
            description="起草电子邮件并保存为草稿",
            risk_level="low",
            fn=draft_email,
        ),
        "send_email": OfficeTool(
            name="send_email",
            description="正式发送电子邮件（高危外部通信操作，默认需人工审批）",
            risk_level="high",
            fn=send_email,
        ),
        "search_company_docs": OfficeTool(
            name="search_company_docs",
            description="检索企业内部制度与架构知识库文档",
            risk_level="low",
            fn=search_company_docs,
        ),
        "web_search": OfficeTool(
            name="web_search",
            description="执行联网检索以获取行业报告与外部技术资料",
            risk_level="low",
            fn=web_search,
        ),
    }


class SQLiteCheckpointer:
    """基于 SQLite 的多 Agent 状态检查点持久化器，支持中断挂起与恢复."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None
        if self.db_path == ":memory:":
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _close_if_file(self, conn: sqlite3.Connection) -> None:
        if self._conn is None:
            conn.close()

    def _init_schema(self) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_checkpoints_thread ON checkpoints(thread_id, created_at)"
            )
            conn.commit()
        finally:
            self._close_if_file(conn)

    def save_checkpoint(self, thread_id: str, state: OfficeState) -> str:
        """保存当前 OfficeState 快照到 SQLite，返回 checkpoint_id."""
        checkpoint_id = f"ckpt-{uuid.uuid4().hex[:12]}"
        now = _utc_now_iso()
        payload = json.dumps(state.to_dict(), ensure_ascii=False)
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO checkpoints (checkpoint_id, thread_id, step_index, status, state_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (checkpoint_id, thread_id, state.current_step_index, state.status, payload, now),
            )
            conn.commit()
        finally:
            self._close_if_file(conn)
        return checkpoint_id

    def load_latest(self, thread_id: str) -> OfficeState | None:
        """读取指定 thread_id 的最新状态快照."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                """
                SELECT state_json FROM checkpoints
                WHERE thread_id = ?
                ORDER BY rowid DESC
                LIMIT 1
                """,
                (thread_id,),
            ).fetchone()
        finally:
            self._close_if_file(conn)

        if row is None:
            return None
        return OfficeState.from_dict(json.loads(row[0]))

    def list_checkpoints(self, thread_id: str) -> list[dict[str, Any]]:
        """列出指定 thread_id 的全部历史检查点元数据."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT checkpoint_id, thread_id, step_index, status, created_at
                FROM checkpoints
                WHERE thread_id = ?
                ORDER BY rowid ASC
                """,
                (thread_id,),
            ).fetchall()
        finally:
            self._close_if_file(conn)

        return [
            {
                "checkpoint_id": r[0],
                "thread_id": r[1],
                "step_index": r[2],
                "status": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


class BaseOfficeAgent:
    """专业办公子 Agent 基类."""

    name: str = "BaseOfficeAgent"
    role: str = "通用办公助手"
    allowed_tools: tuple[str, ...] = ()

    def __init__(self, tools: dict[str, OfficeTool]) -> None:
        self.tools = tools

    def _call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        state: OfficeState,
    ) -> dict[str, Any]:
        if tool_name not in self.allowed_tools:
            raise PermissionError(f"{self.name} 无权调用工具 {tool_name}")
        tool = self.tools[tool_name]
        result = tool.invoke(**arguments)
        record = {
            "agent": self.name,
            "tool": tool_name,
            "arguments": arguments,
            "result": result,
            "timestamp": _utc_now_iso(),
        }
        state.tool_history.append(record)
        return record

    def execute(
        self,
        task: str,
        state: OfficeState,
        interrupt_before: set[str],
        approved_action: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> AgentStepResult:
        raise NotImplementedError


class ResearchAgent(BaseOfficeAgent):
    """资料调研 Agent：负责检索企业内部文档与外部联网资料."""

    name = "ResearchAgent"
    role = "企业知识与行业调研专家"
    allowed_tools = ("search_company_docs", "web_search")

    def execute(
        self,
        task: str,
        state: OfficeState,
        interrupt_before: set[str],
        approved_action: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> AgentStepResult:
        params = params or {}
        query = params.get("query", task)
        tool_calls: list[dict[str, Any]] = []

        doc_rec = self._call_tool("search_company_docs", {"query": query, "top_k": 2}, state)
        tool_calls.append(doc_rec)

        web_rec = self._call_tool("web_search", {"query": query, "top_k": 2}, state)
        tool_calls.append(web_rec)

        doc_titles = [d["title"] for d in doc_rec["result"]["results"]]
        web_titles = [w["title"] for w in web_rec["result"]["results"]]
        summary = (
            f"已检索内部文档 {len(doc_titles)} 篇（{', '.join(doc_titles)}）"
            f"与外部网页 {len(web_titles)} 篇（{', '.join(web_titles)}）。"
        )
        output = {
            "query": query,
            "company_docs": doc_rec["result"]["results"],
            "web_results": web_rec["result"]["results"],
            "summary": summary,
        }
        return AgentStepResult(
            agent_name=self.name,
            summary=summary,
            output=output,
            tool_calls=tool_calls,
        )


class CalendarAgent(BaseOfficeAgent):
    """日程管理 Agent：负责查询日历冲突与创建新会议（create_meeting 支持人工审批中断）."""

    name = "CalendarAgent"
    role = "智能日程与会议协调专员"
    allowed_tools = ("list_calendar", "create_meeting")

    def execute(
        self,
        task: str,
        state: OfficeState,
        interrupt_before: set[str],
        approved_action: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> AgentStepResult:
        params = params or {}
        tool_calls: list[dict[str, Any]] = []

        # 如果是审批恢复阶段，直接执行已批准的 create_meeting
        if approved_action and approved_action.get("tool_name") == "create_meeting":
            args = dict(approved_action["arguments"])
            rec = self._call_tool("create_meeting", args, state)
            tool_calls.append(rec)
            mtg = rec["result"]["meeting"]
            summary = f"人工审批通过，已创建会议 [{mtg['meeting_id']}] {mtg['title']} ({mtg['date']} {mtg['start_time']})。"
            return AgentStepResult(
                agent_name=self.name,
                summary=summary,
                output={"calendar_action": "created", "meeting": mtg},
                tool_calls=tool_calls,
            )

        target_date = params.get("date", "2026-11-16")
        cal_rec = self._call_tool("list_calendar", {"date": target_date}, state)
        tool_calls.append(cal_rec)

        should_create = params.get("create_meeting")
        if should_create is None:
            should_create = any(
                kw in task.lower()
                for kw in ("预约", "创建会议", "安排会议", "新建会议", "schedule", "create_meeting", "book")
            )

        if not should_create:
            count = cal_rec["result"]["count"]
            summary = f"已查询 {target_date} 日程，共 {count} 场已有会议。"
            return AgentStepResult(
                agent_name=self.name,
                summary=summary,
                output={"calendar_action": "listed", "events": cal_rec["result"]["events"]},
                tool_calls=tool_calls,
            )

        meeting_args = {
            "title": params.get("title", "智枢多 Agent 项目对齐会"),
            "date": target_date,
            "start_time": params.get("start_time", "16:00"),
            "attendees": params.get("attendees", ["张工", "林晓", "陈默"]),
            "duration_min": int(params.get("duration_min", 60)),
        }

        if "create_meeting" in interrupt_before:
            pending = PendingAction(
                action_id=f"act-{uuid.uuid4().hex[:10]}",
                agent_name=self.name,
                tool_name="create_meeting",
                arguments=meeting_args,
                reason="创建企业正式会议将占用参会人日程，需人工确认时间与参会人。",
                risk_level="high",
            )
            return AgentStepResult(
                agent_name=self.name,
                summary=f"已检查 {target_date} 日程，准备创建会议《{meeting_args['title']}》，等待人工审批。",
                output={"existing_events": cal_rec["result"]["events"]},
                tool_calls=tool_calls,
                interrupted=True,
                pending_action=pending,
            )

        rec = self._call_tool("create_meeting", meeting_args, state)
        tool_calls.append(rec)
        mtg = rec["result"]["meeting"]
        return AgentStepResult(
            agent_name=self.name,
            summary=f"已创建会议 [{mtg['meeting_id']}] {mtg['title']}。",
            output={"calendar_action": "created", "meeting": mtg},
            tool_calls=tool_calls,
        )


class MailAgent(BaseOfficeAgent):
    """邮件协同 Agent：负责汇总前序 Agent 产出起草邮件，并在发送前触发人工审批中断."""

    name = "MailAgent"
    role = "企业邮件起草与发送专员"
    allowed_tools = ("draft_email", "send_email")

    def execute(
        self,
        task: str,
        state: OfficeState,
        interrupt_before: set[str],
        approved_action: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> AgentStepResult:
        params = params or {}
        tool_calls: list[dict[str, Any]] = []

        # 如果是审批恢复阶段，直接执行已批准的 send_email
        if approved_action and approved_action.get("tool_name") == "send_email":
            args = dict(approved_action["arguments"])
            rec = self._call_tool("send_email", args, state)
            tool_calls.append(rec)
            email = rec["result"]["email"]
            summary = f"人工审批通过，邮件 [{email['email_id']}] 已发送至 {', '.join(email['to'])}。"
            return AgentStepResult(
                agent_name=self.name,
                summary=summary,
                output={"mail_action": "sent", "email": email},
                tool_calls=tool_calls,
            )

        # 汇总前序 Agent 结果生成邮件正文
        context_parts: list[str] = []
        if "ResearchAgent" in state.agent_outputs:
            context_parts.append(f"【调研摘要】{state.agent_outputs['ResearchAgent'].get('summary', '')}")
        if "CalendarAgent" in state.agent_outputs:
            cal_out = state.agent_outputs["CalendarAgent"]
            if "meeting" in cal_out:
                mtg = cal_out["meeting"]
                context_parts.append(
                    f"【会议安排】{mtg['title']}（{mtg['date']} {mtg['start_time']}，参会人：{', '.join(mtg['attendees'])}）"
                )
            elif "events" in cal_out:
                context_parts.append(f"【日程参考】共查询到 {len(cal_out['events'])} 场日程。")

        body = params.get("body") or (
            "各位同事好：\n\n"
            + ("\n".join(context_parts) if context_parts else f"任务说明：{task}")
            + "\n\n请查收并确认，谢谢！"
        )
        to_list = params.get("to", ["linxiao@zhishu.cn", "zhanggong@zhishu.cn"])
        subject = params.get("subject", "【智枢办公助手】项目同步与会议通知")

        draft_rec = self._call_tool(
            "draft_email",
            {"to": to_list, "subject": subject, "body": body},
            state,
        )
        tool_calls.append(draft_rec)
        draft = draft_rec["result"]["draft"]

        should_send = params.get("send_email")
        if should_send is None:
            should_send = any(
                kw in task.lower()
                for kw in ("发送", "发邮件", "邮件通知", "send", "send_email", "notify")
            )

        if not should_send:
            return AgentStepResult(
                agent_name=self.name,
                summary=f"已生成邮件草稿 [{draft['draft_id']}]：《{subject}》。",
                output={"mail_action": "drafted", "draft": draft},
                tool_calls=tool_calls,
            )

        send_args = {
            "to": to_list,
            "subject": subject,
            "body": body,
            "draft_id": draft["draft_id"],
        }

        if "send_email" in interrupt_before:
            pending = PendingAction(
                action_id=f"act-{uuid.uuid4().hex[:10]}",
                agent_name=self.name,
                tool_name="send_email",
                arguments=send_args,
                reason="正式发送电子邮件属于不可逆外部通信操作，需人工核对收件人与正文内容。",
                risk_level="high",
            )
            return AgentStepResult(
                agent_name=self.name,
                summary=f"已生成草稿 [{draft['draft_id']}]，准备执行 send_email，等待人工审批。",
                output={"draft": draft},
                tool_calls=tool_calls,
                interrupted=True,
                pending_action=pending,
            )

        send_rec = self._call_tool("send_email", send_args, state)
        tool_calls.append(send_rec)
        email = send_rec["result"]["email"]
        return AgentStepResult(
            agent_name=self.name,
            summary=f"邮件 [{email['email_id']}] 已直接发送至 {', '.join(email['to'])}。",
            output={"mail_action": "sent", "email": email},
            tool_calls=tool_calls,
        )


class OfficeSupervisor:
    """多 Agent 智能办公主管：负责意图拆解、路由调度、SQLite 断点保存与审批恢复."""

    def __init__(
        self,
        workspace: OfficeWorkspace | None = None,
        checkpointer: SQLiteCheckpointer | None = None,
        interrupt_before: set[str] | list[str] | None = None,
    ) -> None:
        self.workspace = workspace or OfficeWorkspace()
        self.tools = create_default_tools(self.workspace)
        self.checkpointer = checkpointer or SQLiteCheckpointer(":memory:")
        if interrupt_before is None:
            self.interrupt_before: set[str] = {"send_email", "create_meeting"}
        else:
            self.interrupt_before = set(interrupt_before)

        self.agents: dict[str, BaseOfficeAgent] = {
            "ResearchAgent": ResearchAgent(self.tools),
            "CalendarAgent": CalendarAgent(self.tools),
            "MailAgent": MailAgent(self.tools),
        }

    def plan_tasks(self, user_request: str) -> list[dict[str, Any]]:
        """根据用户自然语言请求拆解多 Agent 协同执行计划."""
        lowered = user_request.lower()
        plan: list[dict[str, Any]] = []

        if any(kw in lowered for kw in ("调研", "文档", "制度", "资料", "搜索", "规划", "research", "doc", "search")):
            plan.append({"agent": "ResearchAgent", "task": user_request, "params": {}})

        if any(kw in lowered for kw in ("日程", "日历", "会议", "预约", "安排", "calendar", "meeting", "schedule")):
            plan.append({"agent": "CalendarAgent", "task": user_request, "params": {}})

        if any(kw in lowered for kw in ("邮件", "草拟", "起草", "发送", "通知", "email", "mail", "send")):
            plan.append({"agent": "MailAgent", "task": user_request, "params": {}})

        if not plan:
            plan.append({"agent": "ResearchAgent", "task": user_request, "params": {}})

        return plan

    def _run_from_current_step(self, state: OfficeState) -> dict[str, Any]:
        """从 state.current_step_index 继续执行计划中的各 Agent 步骤."""
        while state.current_step_index < len(state.plan):
            step = state.plan[state.current_step_index]
            agent_name = step["agent"]
            agent = self.agents.get(agent_name)
            if agent is None:
                state.status = TaskStatus.FAILED.value
                state.error = f"未知的 Agent: {agent_name}"
                ckpt_id = self.checkpointer.save_checkpoint(state.thread_id, state)
                return self._build_response(state, ckpt_id)

            step_result = agent.execute(
                task=step.get("task", state.user_request),
                state=state,
                interrupt_before=self.interrupt_before,
                params=step.get("params"),
            )

            if step_result.output:
                state.agent_outputs[agent_name] = step_result.output

            if step_result.interrupted and step_result.pending_action is not None:
                state.status = TaskStatus.INTERRUPTED.value
                state.pending_action = step_result.pending_action.to_dict()
                ckpt_id = self.checkpointer.save_checkpoint(state.thread_id, state)
                return self._build_response(state, ckpt_id)

            state.current_step_index += 1
            self.checkpointer.save_checkpoint(state.thread_id, state)

        state.status = TaskStatus.COMPLETED.value
        state.pending_action = None
        state.final_response = self._synthesize_final_response(state)
        ckpt_id = self.checkpointer.save_checkpoint(state.thread_id, state)
        return self._build_response(state, ckpt_id)

    def _synthesize_final_response(self, state: OfficeState) -> str:
        lines = [f"已完成办公协同请求：{state.user_request}"]
        for agent_name, out in state.agent_outputs.items():
            if "summary" in out:
                lines.append(f"- [{agent_name}] {out['summary']}")
            elif "meeting" in out:
                m = out["meeting"]
                lines.append(f"- [{agent_name}] 已创建会议 {m['meeting_id']}: {m['title']} ({m['date']} {m['start_time']})")
            elif "email" in out:
                e = out["email"]
                lines.append(f"- [{agent_name}] 已发送邮件 {e['email_id']} 至 {', '.join(e['to'])}")
            elif "draft" in out:
                d = out["draft"]
                lines.append(f"- [{agent_name}] 已生成草稿 {d['draft_id']}: {d['subject']}")
        return "\n".join(lines)

    def _build_response(self, state: OfficeState, checkpoint_id: str) -> dict[str, Any]:
        return {
            "thread_id": state.thread_id,
            "checkpoint_id": checkpoint_id,
            "status": state.status,
            "current_step_index": state.current_step_index,
            "total_steps": len(state.plan),
            "pending_action": state.pending_action,
            "agent_outputs": state.agent_outputs,
            "final_response": state.final_response,
            "error": state.error,
        }

    def run(
        self,
        user_request: str,
        thread_id: str | None = None,
        custom_plan: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """启动一次新的多 Agent 智能办公任务."""
        tid = thread_id or f"thread-{uuid.uuid4().hex[:10]}"
        plan = custom_plan if custom_plan is not None else self.plan_tasks(user_request)
        state = OfficeState(
            thread_id=tid,
            user_request=user_request,
            status=TaskStatus.RUNNING.value,
            plan=plan,
            current_step_index=0,
        )
        self.checkpointer.save_checkpoint(tid, state)
        return self._run_from_current_step(state)

    def resume(
        self,
        thread_id: str,
        approved: bool = True,
        modified_args: dict[str, Any] | None = None,
        feedback: str = "",
    ) -> dict[str, Any]:
        """从 SQLite 检查点恢复被高危操作中断的办公任务."""
        state = self.checkpointer.load_latest(thread_id)
        if state is None:
            raise ValueError(f"未找到 thread_id={thread_id} 的检查点记录")
        if state.status != TaskStatus.INTERRUPTED.value or state.pending_action is None:
            raise ValueError(f"thread_id={thread_id} 当前状态为 {state.status}，无法执行审批恢复")

        pending = dict(state.pending_action)
        state.approval_history.append(
            {
                "action_id": pending["action_id"],
                "tool_name": pending["tool_name"],
                "approved": approved,
                "modified_args": modified_args,
                "feedback": feedback,
                "decided_at": _utc_now_iso(),
            }
        )

        if not approved:
            state.status = TaskStatus.REJECTED.value
            state.pending_action = None
            state.final_response = f"操作 {pending['tool_name']} 已被人工拒绝：{feedback or '用户取消执行'}"
            ckpt_id = self.checkpointer.save_checkpoint(thread_id, state)
            return self._build_response(state, ckpt_id)

        if modified_args:
            merged_args = dict(pending["arguments"])
            merged_args.update(modified_args)
            pending["arguments"] = merged_args

        agent_name = pending["agent_name"]
        agent = self.agents[agent_name]
        step = state.plan[state.current_step_index]

        state.status = TaskStatus.RUNNING.value
        state.pending_action = None

        step_result = agent.execute(
            task=step.get("task", state.user_request),
            state=state,
            interrupt_before=self.interrupt_before,
            approved_action=pending,
            params=step.get("params"),
        )
        if step_result.output:
            state.agent_outputs[agent_name] = step_result.output

        state.current_step_index += 1
        self.checkpointer.save_checkpoint(thread_id, state)
        return self._run_from_current_step(state)

    def get_state(self, thread_id: str) -> OfficeState | None:
        return self.checkpointer.load_latest(thread_id)

    def get_history(self, thread_id: str) -> list[dict[str, Any]]:
        return self.checkpointer.list_checkpoints(thread_id)
