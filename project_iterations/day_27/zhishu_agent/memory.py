"""智枢平台 Day 27 核心模块：多会话记忆管理、窗口裁剪、摘要压缩与 SQLite 会话隔离。"""
from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

VALID_ROLES = frozenset({"system", "user", "assistant"})


def _utc_now_iso() -> str:
    """返回当前 UTC ISO-8601 时间戳。"""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ChatMessage:
    """标准对话消息数据结构。"""

    role: str
    content: str
    created_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self) -> None:
        if self.role not in VALID_ROLES:
            raise ValueError(f"不支持的消息角色: {self.role!r}，允许值为 {sorted(VALID_ROLES)}")

    def to_dict(self) -> dict[str, str]:
        """转换为标准字典格式，便于序列化或传给大模型 API。"""
        return {
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
        }


class BaseChatMessageHistory(ABC):
    """对话历史存储抽象基类（对标 LangChain BaseChatMessageHistory）。"""

    @property
    @abstractmethod
    def messages(self) -> list[ChatMessage]:
        """按时间正序返回当前会话的所有消息。"""

    @abstractmethod
    def add_message(self, message: ChatMessage) -> None:
        """向当前会话追加一条消息。"""

    def add_user_message(self, content: str) -> None:
        """快捷追加一条用户消息。"""
        self.add_message(ChatMessage(role="user", content=content))

    def add_ai_message(self, content: str) -> None:
        """快捷追加一条助手消息。"""
        self.add_message(ChatMessage(role="assistant", content=content))

    def add_system_message(self, content: str) -> None:
        """快捷追加一条系统消息。"""
        self.add_message(ChatMessage(role="system", content=content))

    @abstractmethod
    def clear(self) -> None:
        """清空当前会话的所有历史消息。"""


class InMemoryChatMessageHistory(BaseChatMessageHistory):
    """基于内存列表的对话历史存储，适用于单次运行与快速单元测试。"""

    def __init__(self, initial_messages: Sequence[ChatMessage] | None = None) -> None:
        self._messages: list[ChatMessage] = list(initial_messages) if initial_messages else []

    @property
    def messages(self) -> list[ChatMessage]:
        return list(self._messages)

    def add_message(self, message: ChatMessage) -> None:
        self._messages.append(message)

    def clear(self) -> None:
        self._messages.clear()


class SQLiteChatMessageHistory(BaseChatMessageHistory):
    """基于 SQLite 的持久化对话历史存储，按 session_id 严格隔离多租户会话。"""

    def __init__(self, session_id: str, db_path: str | Path) -> None:
        if not session_id or not session_id.strip():
            raise ValueError("session_id 不能为空")
        self.session_id = session_id.strip()
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('system', 'user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id
                ON chat_messages(session_id, id)
                """
            )

    @property
    def messages(self) -> list[ChatMessage]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (self.session_id,),
            ).fetchall()
        return [
            ChatMessage(role=row["role"], content=row["content"], created_at=row["created_at"])
            for row in rows
        ]

    def add_message(self, message: ChatMessage) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (self.session_id, message.role, message.content, message.created_at),
            )

    def clear(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM chat_messages WHERE session_id = ?",
                (self.session_id,),
            )

    @classmethod
    def list_sessions(cls, db_path: str | Path) -> list[str]:
        """列出数据库中所有存在消息的 session_id（按字母序）。"""
        path = Path(db_path)
        if not path.exists():
            return []
        with sqlite3.connect(path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT session_id FROM chat_messages ORDER BY session_id ASC"
            ).fetchall()
        return [row[0] for row in rows]


class WindowMemory:
    """滑动窗口记忆：仅保留最近 k 轮对话（每轮按 2 条消息计算），可选保留系统提示词。"""

    def __init__(self, k: int = 3, keep_system: bool = True) -> None:
        if k < 0:
            raise ValueError("窗口大小 k 不能为负数")
        self.k = k
        self.keep_system = keep_system

    def trim_messages(self, messages: Sequence[ChatMessage]) -> list[ChatMessage]:
        """对消息列表执行滑动窗口裁剪，保持时间正序。"""
        system_msgs = [m for m in messages if m.role == "system"] if self.keep_system else []
        conv_msgs = [m for m in messages if m.role != "system"]
        if self.k == 0:
            recent_msgs: list[ChatMessage] = []
        else:
            recent_msgs = list(conv_msgs[-(self.k * 2) :])
        return [*system_msgs, *recent_msgs]

    def load_memory_variables(self, history: BaseChatMessageHistory) -> list[ChatMessage]:
        """从历史仓储中加载经过窗口裁剪的消息列表。"""
        return self.trim_messages(history.messages)


def _default_summarizer(older_messages: Sequence[ChatMessage], previous_summary: str) -> str:
    """内置确定性摘要器：无需外部大模型即可将早期对话压缩为结构化摘要。"""
    snippets: list[str] = []
    if previous_summary:
        snippets.append(previous_summary)
    for msg in older_messages:
        speaker = "用户" if msg.role == "user" else ("助手" if msg.role == "assistant" else "系统")
        compact = " ".join(msg.content.strip().split())
        if len(compact) > 60:
            compact = compact[:57] + "..."
        snippets.append(f"{speaker}: {compact}")
    return " | ".join(snippets)


class SummaryMemory:
    """摘要记忆：保留最近 max_recent_messages 条消息，将更早的对话压缩为一条系统摘要。"""

    def __init__(
        self,
        max_recent_messages: int = 4,
        summarizer: Callable[[Sequence[ChatMessage], str], str] | None = None,
        summary_prefix: str = "历史对话摘要：",
    ) -> None:
        if max_recent_messages < 0:
            raise ValueError("max_recent_messages 不能为负数")
        self.max_recent_messages = max_recent_messages
        self.summarizer = summarizer or _default_summarizer
        self.summary_prefix = summary_prefix
        self.moving_summary: str = ""

    def load_memory_variables(self, history: BaseChatMessageHistory) -> dict[str, Any]:
        """计算并返回摘要文本、近期消息以及合并后的完整上下文消息列表。"""
        all_msgs = [m for m in history.messages if m.role != "system"]
        if self.max_recent_messages == 0:
            older_msgs = all_msgs
            recent_msgs: list[ChatMessage] = []
        elif len(all_msgs) > self.max_recent_messages:
            split_idx = len(all_msgs) - self.max_recent_messages
            older_msgs = all_msgs[:split_idx]
            recent_msgs = all_msgs[split_idx:]
        else:
            older_msgs = []
            recent_msgs = all_msgs

        if older_msgs:
            summary_body = self.summarizer(older_msgs, "")
            self.moving_summary = f"{self.summary_prefix}{summary_body}"
            merged = [ChatMessage(role="system", content=self.moving_summary), *recent_msgs]
        else:
            self.moving_summary = ""
            merged = list(recent_msgs)

        return {
            "summary": self.moving_summary,
            "recent_messages": recent_msgs,
            "messages": merged,
        }


class RunnableWithMessageHistory:
    """带会话历史管理的可执行包装器（对标 LangChain RunnableWithMessageHistory）。"""

    def __init__(
        self,
        runnable: Callable[[dict[str, Any]], str],
        get_session_history: Callable[[str], BaseChatMessageHistory],
        memory_strategy: WindowMemory | SummaryMemory | None = None,
    ) -> None:
        self.runnable = runnable
        self.get_session_history = get_session_history
        self.memory_strategy = memory_strategy

    def _resolve_session_id(
        self,
        config: dict[str, Any] | None,
        session_id: str | None,
    ) -> str:
        sid = session_id
        if sid is None and config is not None:
            sid = config.get("configurable", {}).get("session_id")
        if not sid or not str(sid).strip():
            raise ValueError("必须通过 session_id 或 config['configurable']['session_id'] 指定会话 ID")
        return str(sid).strip()

    def _build_context(self, history: BaseChatMessageHistory) -> list[ChatMessage]:
        if isinstance(self.memory_strategy, WindowMemory):
            return self.memory_strategy.load_memory_variables(history)
        if isinstance(self.memory_strategy, SummaryMemory):
            return self.memory_strategy.load_memory_variables(history)["messages"]
        return history.messages

    def invoke(
        self,
        input_data: dict[str, Any] | str,
        config: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> str:
        """按 session_id 加载历史上下文、调用链并自动落库本轮对话。"""
        sid = self._resolve_session_id(config, session_id)
        user_input = input_data if isinstance(input_data, str) else str(input_data.get("input", ""))
        history = self.get_session_history(sid)
        context_messages = self._build_context(history)

        payload: dict[str, Any] = {
            "input": user_input,
            "history": context_messages,
            "session_id": sid,
        }
        if isinstance(input_data, dict):
            for key, value in input_data.items():
                if key not in payload:
                    payload[key] = value

        ai_reply = self.runnable(payload)
        history.add_user_message(user_input)
        history.add_ai_message(ai_reply)
        return ai_reply
